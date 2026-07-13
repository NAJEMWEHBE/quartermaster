# -*- coding: utf-8 -*-
"""Index build + query, with a fake in-process embedder (no network / no Ollama)."""
import json
import re
import sys

import assemble_catalog
import build_index
import query_arsenal
from entry import Entry

# a tiny deterministic bag-of-words 'embedder' over a fixed vocab
VOCAB = ["foo", "bar", "baz", "route", "embed", "test", "widget", "need"]


def fake_embed(texts, timeout=120):
    out = []
    for t in texts:
        toks = re.findall(r"[a-z0-9]+", t.lower())
        v = [float(sum(1 for tok in toks if tok == w)) for w in VOCAB]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / n for x in v])
    return out


def test_invoke_name_colon_preference():
    assert build_index.invoke_name(Entry(id="x", name="plugin:skill")) == "plugin:skill"
    assert build_index.invoke_name(Entry(id="x", name="Plain")) == "x"     # no colon -> id
    assert build_index.invoke_name(Entry(id="", name="Plain")) == "Plain"  # no id -> name


def test_build_index_and_query(qm_env, monkeypatch, capsys):
    assemble_catalog.main()
    capsys.readouterr()  # drop assemble output

    # build the index with the fake embedder (build_index bound `embed` at import time)
    monkeypatch.setattr(build_index, "embed", fake_embed)
    assert build_index.main() == 0
    capsys.readouterr()

    meta = json.loads((qm_env / "arsenal_index.meta.json").read_text(encoding="utf-8"))
    # only skill-kind entries are indexed (foo, nonascii, route-noptn, missingfields)
    assert meta["count"] == 4
    assert meta["dim"] == len(VOCAB)
    assert set(meta["ids"]) == {"foo", "nonascii", "route-noptn", "missingfields"}
    # none of these names contain ':', so invoke_name falls back to the id
    assert meta["names"] == meta["ids"]

    # query with the defensive normalization path
    monkeypatch.setattr(query_arsenal, "embed", fake_embed)
    monkeypatch.setattr(sys, "argv", ["query_arsenal.py", "foo"])
    assert query_arsenal.main() == 0
    out = capsys.readouterr().out
    assert "Foo" in out and "Arsenal matches for: foo" in out
