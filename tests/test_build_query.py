# -*- coding: utf-8 -*-
"""Index build + query through the CLI seam, with a fake in-process embedder (no
network, no Ollama)."""
import datetime
import json
import re
import urllib.error

from conftest import FakeEmbedder, write_json
from quartermaster import cli, index
from quartermaster.entry import Entry

# a tiny deterministic bag-of-words 'embedder' over a fixed vocab
VOCAB = ["foo", "bar", "baz", "route", "embed", "test", "widget", "need", "second", "agent"]


def bag_of_words(texts):
    out = []
    for t in texts:
        toks = re.findall(r"[a-z0-9]+", t.lower())
        v = [float(sum(1 for tok in toks if tok == w)) for w in VOCAB]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / n for x in v])
    return out


fake_embed = FakeEmbedder(bag_of_words)


def test_invoke_name_colon_preference():
    assert index.invoke_name(Entry(id="x", name="plugin:skill")) == "plugin:skill"
    assert index.invoke_name(Entry(id="x", name="Plain")) == "x"     # no colon -> id
    assert index.invoke_name(Entry(id="", name="Plain")) == "Plain"  # no id -> name


def _built_index(qm_env, capsys):
    cli.assemble_main([])
    assert cli.build_index_main([], embed=fake_embed) == 0
    capsys.readouterr()


def _query(capsys, embedder, *argv):
    rc = cli.query_main(list(argv), embed=embedder)
    return rc, capsys.readouterr()


def test_build_index_and_query(qm_env, capsys):
    _built_index(qm_env, capsys)
    meta = json.loads((qm_env / "arsenal_index.meta.json").read_text(encoding="utf-8"))
    assert meta["dim"] == len(VOCAB)
    assert meta["model"] == "qwen3-embedding:0.6b"  # the embedder's model, checked at query time

    rc, out = _query(capsys, fake_embed, "foo")
    assert rc == 0
    assert "Foo" in out.out and "Arsenal matches for: foo" in out.out


def test_every_kind_is_indexed_and_found(qm_env, capsys):
    """'Which agent ...' must be able to match an agent, not only skills."""
    _built_index(qm_env, capsys)
    meta = json.loads((qm_env / "arsenal_index.meta.json").read_text(encoding="utf-8"))
    assert set(meta["kinds"]) == {"skill", "plugin", "model", "agent"}
    assert ("agent", "second") in set(zip(meta["kinds"], meta["ids"]))

    rc, out = _query(capsys, fake_embed, "second agent")
    assert rc == 0
    assert "## Second  `agent`" in out.out


def test_results_show_how_to_invoke_a_skill(qm_env, capsys):
    write_json(qm_env / "entries" / "batch-00-plugin.json", [
        {"id": "pr-widget", "kind": "skill", "name": "toolkit:pr-widget", "what": "widget widget",
         "use_when": "widget", "avoid_when": "a", "tier": "catalog"}])
    _built_index(qm_env, capsys)
    rc, out = _query(capsys, fake_embed, "widget")
    assert rc == 0
    assert "**Invoke:** `/toolkit:pr-widget`" in out.out


def test_results_say_how_old_the_catalog_is(qm_env, capsys):
    _built_index(qm_env, capsys)
    rc, out = _query(capsys, fake_embed, "foo")
    assert "catalog generated" in out.out and "days old" not in out.out

    cat = json.loads((qm_env / "arsenal.json").read_text(encoding="utf-8"))
    cat["generated"] = (datetime.datetime.now() - datetime.timedelta(days=30)).isoformat(timespec="seconds")
    write_json(qm_env / "arsenal.json", cat)
    rc, out = _query(capsys, fake_embed, "foo")
    assert rc == 0 and "Catalog is 30 days old" in out.out


def test_query_instruction_is_opt_in(qm_env, capsys):
    seen = []
    spy = FakeEmbedder(lambda texts: (seen.extend(texts), bag_of_words(texts))[1])
    _built_index(qm_env, capsys)
    _query(capsys, spy, "foo")
    assert seen == ["foo"]  # default: the query as typed

    cfg_path = qm_env.parent / "quartermaster.config.json"
    c = json.loads(cfg_path.read_text(encoding="utf-8"))
    c["embed"]["query_instruction"] = "Find the installed tool for this need"
    write_json(cfg_path, c)
    seen.clear()
    _query(capsys, spy, "foo")
    assert seen == ["Instruct: Find the installed tool for this need\nQuery: foo"]


def test_query_missing_catalog_degrades(qm_env, capsys):
    # no assemble ran -> no arsenal.json in the work dir: must exit 3 with the
    # CATALOG-UNAVAILABLE message, never an uncaught FileNotFoundError. (Exit 2 is
    # reserved for "embedding down, read arsenal.json instead", which can't apply here.)
    rc, out = _query(capsys, fake_embed, "anything at all")
    assert rc == 3
    assert "CATALOG-UNAVAILABLE" in out.err
    assert "QUARTERMASTER_CONFIG" in out.out


def test_query_returns_the_skill_not_a_same_id_plugin(qm_env, capsys):
    write_json(qm_env / "entries" / "batch-00-kinds.json", [
        {"id": "widget", "kind": "plugin", "name": "widget", "what": "PLUGIN-WIDGET",
         "use_when": "u", "avoid_when": "a", "tier": "catalog"},
        {"id": "widget", "kind": "skill", "name": "widget", "what": "SKILL-WIDGET",
         "use_when": "widget widget", "avoid_when": "a", "tier": "catalog"},
    ])
    _built_index(qm_env, capsys)
    rc, out = _query(capsys, fake_embed, "--k", "1", "widget")
    assert rc == 0
    assert "SKILL-WIDGET" in out.out and "PLUGIN-WIDGET" not in out.out

    rc, out = _query(capsys, fake_embed, "--explain", "widget")
    assert rc == 0
    assert "SKILL-WIDGET" in out.out and "PLUGIN-WIDGET" in out.out  # one id, two tools: show both


def test_index_built_with_another_model_is_stale_not_embedding_down(qm_env, capsys):
    """Same-dimension model swaps used to return wrong rankings silently."""
    _built_index(qm_env, capsys)

    def must_not_embed(texts):
        raise AssertionError("a stale index must be caught before embedding the query")

    rc, out = _query(capsys, FakeEmbedder(must_not_embed, model="some-other-embedder:1b"), "foo")
    assert rc == 4
    assert "INDEX-STALE" in out.err and "EMBEDDING-UNAVAILABLE" not in out.err
    assert "--rebuild-index" in out.out


def test_query_vector_of_another_size_is_stale(qm_env, capsys):
    _built_index(qm_env, capsys)
    rc, out = _query(capsys, FakeEmbedder(lambda texts: [[1.0, 0.0, 0.0, 0.0]]), "foo")
    assert rc == 4 and "INDEX-STALE" in out.err


def test_missing_index_is_stale(qm_env, capsys):
    cli.assemble_main([])
    capsys.readouterr()
    rc, out = _query(capsys, fake_embed, "foo")
    assert rc == 4 and "INDEX-STALE" in out.err


def test_unreachable_embedder_is_embedding_unavailable(qm_env, capsys):
    _built_index(qm_env, capsys)

    def down(texts):
        raise urllib.error.URLError("connection refused")

    rc, out = _query(capsys, FakeEmbedder(down), "foo")
    assert rc == 2 and "EMBEDDING-UNAVAILABLE" in out.err
    assert "arsenal.json" in out.out


def test_old_catalog_location_is_pointed_out(qm_env, capsys, monkeypatch, tmp_path):
    """Upgraders whose data sits in the engine's old ./data folder get told where it is."""
    from quartermaster import config
    engine = tmp_path / "engine"
    (engine / "data").mkdir(parents=True)
    (engine / "data" / "arsenal.json").write_text('{"items": []}', encoding="utf-8")
    monkeypatch.setattr(config, "ENGINE_DIR", str(engine))
    rc, out = _query(capsys, fake_embed, "foo")
    assert rc == 3 and str(engine / "data" / "arsenal.json") in out.out


def test_a_model_that_was_never_pulled_is_named(qm_env, capsys):
    """Ollama answers 404 for an unknown model; that's a missing pull, not a down server."""
    import io
    _built_index(qm_env, capsys)

    def not_pulled(texts):
        raise urllib.error.HTTPError("http://127.0.0.1:11434/api/embed", 404, "Not Found", {},
                                     io.BytesIO(b'{"error":"model not found"}'))

    rc, out = _query(capsys, FakeEmbedder(not_pulled), "foo")
    assert rc == 2 and "EMBEDDING-UNAVAILABLE" in out.err
    assert "ollama pull qwen3-embedding:0.6b" in out.out
