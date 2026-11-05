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


def test_query_missing_catalog_degrades(qm_env, monkeypatch, capsys):
    # no assemble ran -> no arsenal.json in the work dir: must exit 3 with the
    # CATALOG-UNAVAILABLE message, never an uncaught FileNotFoundError. (Exit 2 is
    # reserved for "embedding down, read arsenal.json instead", which can't apply here.)
    monkeypatch.setattr(sys, "argv", ["query_arsenal.py", "anything at all"])
    assert query_arsenal.main() == 3
    err = capsys.readouterr()
    assert "CATALOG-UNAVAILABLE" in err.err
    assert "QUARTERMASTER_CONFIG" in err.out


def test_query_returns_the_skill_not_a_same_id_plugin(qm_env, monkeypatch, capsys):
    from conftest import write_json
    write_json(qm_env / "entries" / "batch-00-kinds.json", [
        {"id": "widget", "kind": "plugin", "name": "widget", "what": "PLUGIN-WIDGET",
         "use_when": "u", "avoid_when": "a", "tier": "catalog"},
        {"id": "widget", "kind": "skill", "name": "widget", "what": "SKILL-WIDGET",
         "use_when": "widget widget", "avoid_when": "a", "tier": "catalog"},
    ])
    assemble_catalog.main()
    monkeypatch.setattr(build_index, "embed", fake_embed)
    assert build_index.main() == 0
    monkeypatch.setattr(query_arsenal, "embed", fake_embed)
    monkeypatch.setattr(sys, "argv", ["query_arsenal.py", "widget"])
    capsys.readouterr()
    assert query_arsenal.main() == 0
    out = capsys.readouterr().out
    assert "SKILL-WIDGET" in out and "PLUGIN-WIDGET" not in out

    monkeypatch.setattr(sys, "argv", ["query_arsenal.py", "--explain", "widget"])
    assert query_arsenal.main() == 0
    out = capsys.readouterr().out
    assert "SKILL-WIDGET" in out and "PLUGIN-WIDGET" in out  # one id, two tools: show both


def _built_index(qm_env, monkeypatch, capsys):
    assemble_catalog.main()
    monkeypatch.setattr(build_index, "embed", fake_embed)
    assert build_index.main() == 0
    capsys.readouterr()


def _query(monkeypatch, capsys, embedder, *argv):
    monkeypatch.setattr(query_arsenal, "embed", embedder)
    monkeypatch.setattr(sys, "argv", ["query_arsenal.py", *argv])
    rc = query_arsenal.main()
    return rc, capsys.readouterr()


def test_index_built_with_another_model_is_stale_not_embedding_down(qm_env, monkeypatch, capsys):
    """Same-dimension model swaps used to return wrong rankings silently."""
    import config
    _built_index(qm_env, monkeypatch, capsys)
    config.cfg()["embed"]["model"] = "some-other-embedder:1b"

    def must_not_embed(texts, timeout=120):
        raise AssertionError("a stale index must be caught before embedding the query")

    rc, out = _query(monkeypatch, capsys, must_not_embed, "foo")
    assert rc == 4
    assert "INDEX-STALE" in out.err and "EMBEDDING-UNAVAILABLE" not in out.err
    assert "--rebuild-index" in out.out


def test_query_vector_of_another_size_is_stale(qm_env, monkeypatch, capsys):
    _built_index(qm_env, monkeypatch, capsys)
    rc, out = _query(monkeypatch, capsys, lambda texts, timeout=120: [[1.0, 0.0, 0.0, 0.0]], "foo")
    assert rc == 4 and "INDEX-STALE" in out.err


def test_missing_index_is_stale(qm_env, monkeypatch, capsys):
    assemble_catalog.main()
    capsys.readouterr()
    rc, out = _query(monkeypatch, capsys, fake_embed, "foo")
    assert rc == 4 and "INDEX-STALE" in out.err


def test_unreachable_embedder_is_embedding_unavailable(qm_env, monkeypatch, capsys):
    import urllib.error
    _built_index(qm_env, monkeypatch, capsys)

    def down(texts, timeout=120):
        raise urllib.error.URLError("connection refused")

    rc, out = _query(monkeypatch, capsys, down, "foo")
    assert rc == 2 and "EMBEDDING-UNAVAILABLE" in out.err
    assert "arsenal.json" in out.out
