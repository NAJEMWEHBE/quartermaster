# -*- coding: utf-8 -*-
"""Text from installed tools, study-agent entry files and the embedding server is input,
not trusted output: it is shown inert on the console and in the log, odd values cost one
entry or one item rather than the scheduled run, plugin skill paths stay inside the
plugin, the index answers only when its two files come from one build, and --explain
explains only the tool that was named."""
import json
import os
import random
import re
import subprocess
import sys
import time

import pytest

from conftest import FakeEmbedder, write_json
from quartermaster import cli, config, inventory, matching, pipeline, workspace
from quartermaster.workspace import Workspace, term_safe
from test_build_query import _query, fake_embed
from test_enumerate import (_FakeResponse, _configure_scan, _enumerated_skills,
                            _fake_claude_home, _no_subprocess, _only, _plugin, _skill_md)

ESC = "\x1b"
RAW_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


# --- terminal control characters ------------------------------------------------------

def test_term_safe_shows_controls_and_keeps_text():
    s = "a\x1b[2Jb\x07c\rd\x9b e\x7f f\tg\nh, مرحبا"
    assert term_safe(s) == "a\\x1b[2Jb\\x07c\\x0dd\\x9b e\\x7f f\tg\nh, مرحبا"


def test_one_log_call_is_one_inert_line(tmp_path, capsys):
    ws = Workspace(str(tmp_path), "w.log")
    ws.log("step\nFAKE: done\x1b]0;title\x07")
    out = capsys.readouterr().out
    log = (tmp_path / "w.log").read_text(encoding="utf-8")
    for text in (out, log):
        assert not RAW_CONTROL.search(text)
        assert len(text.strip().splitlines()) == 1
        assert "step\\nFAKE: done\\x1b]0;title\\x07" in text


def test_catalog_text_is_inert_in_query_output_and_arsenal_md(qm_env, capsys):
    write_json(qm_env / "entries" / "batch-00-ansi.json", [
        {"id": "ansi", "kind": "skill", "name": "ansi\x1b[8m", "tier": "catalog",
         "what": "w\x1b]8;;file:x\x07link\x1b]8;;\x07", "use_when": "u\x1b[2J",
         "avoid_when": "a\x9b31m", "triggers": ["t\x07"]}])
    assert cli.assemble_main([]) == 0
    capsys.readouterr()
    rc, out = _query(capsys, fake_embed, "--explain", "ansi")
    assert rc == 0 and "\\x1b]8;;file:x\\x07link" in out.out
    md = (qm_env / "ARSENAL.md").read_text(encoding="utf-8")
    for text in (out.out, md):
        assert not RAW_CONTROL.search(text)


def test_error_text_from_peers_is_inert(qm_env, capsys, monkeypatch):
    cli.assemble_main([])
    capsys.readouterr()

    def broken(texts):
        raise RuntimeError("server says \x1b[2J\x1b]0;x\x07")

    assert cli.build_index_main([], embed=FakeEmbedder(broken)) == 1
    err = capsys.readouterr().err
    assert "build_index FAILED" in err and ESC not in err and "\\x1b[2J" in err

    assert cli.build_index_main([], embed=fake_embed) == 0

    def down(texts):
        raise OSError("refused \x1b[2J")

    capsys.readouterr()
    rc, out = _query(capsys, FakeEmbedder(down), "need")
    assert rc == cli.EXIT_EMBEDDING_DOWN and ESC not in out.err and "\\x1b[2J" in out.err

    def refused(url, timeout=None):
        raise OSError("refused \x1b[2J")

    monkeypatch.setattr(inventory.urllib.request, "urlopen", refused)
    assert inventory.ollama_models() == []
    err = capsys.readouterr().err
    assert ESC not in err and "\\x1b[2J" in err


# --- the match key ----------------------------------------------------------------------

def test_nkey_keeps_the_old_rule_in_linear_time():
    old = lambda s: re.sub(r"\(.*?\)", "", s)  # noqa: E731
    rng = random.Random(7)
    cases = ["foo (plugin)", "foo (a (b) c)", "a(\nb)c", "((x)", "a)b(c", "(\n)", "", "plain"]
    cases += ["".join(rng.choice("ab()\n ") for _ in range(rng.randrange(30))) for _ in range(3000)]
    for s in cases:
        assert matching._drop_parentheticals(s) == old(s), repr(s)
    assert matching.nkey("foo (plugin)") == "foo"
    for s in ("(" * 200000, "(\n" * 100000 + ")", "(a" * 100000):
        t = time.perf_counter()
        matching.nkey(s)
        assert time.perf_counter() - t < 1.0


# --- entry files from study agents ------------------------------------------------------

def test_odd_json_in_an_entry_file_costs_that_entry_nothing_more(qm_env, capsys):
    odd = [{"id": 7, "kind": ["skill"], "name": {"x": 1}, "what": "\ud800 half",
            "triggers": [1, None, {"a": 1}, "t"], "offline": "yes", "route_patterns": "p",
            "tier": ["route"]},
           {"id": "fine", "kind": "skill", "name": "fine", "what": "ok", "tier": "catalog"}]
    # json.dumps keeps the lone surrogate as a \ud800 escape, as a study agent might
    (qm_env / "entries" / "batch-00-odd.json").write_text(json.dumps(odd), encoding="utf-8")
    (qm_env / "entries" / "batch-00-deep.json").write_text("[" * 100000 + "]" * 100000,
                                                           encoding="utf-8")
    assert cli.assemble_main([]) == 0
    cat = json.loads((qm_env / "arsenal.json").read_text(encoding="utf-8"))
    e = next(i for i in cat["items"] if i["id"] == "7")
    assert (e["kind"], e["name"], e["what"], e["offline"]) == ("", "", "? half", "")
    assert e["triggers"] == ["1", "t"] and e["route_patterns"] == ["p"] and e["tier"] == "catalog"
    assert any(i["id"] == "fine" for i in cat["items"])
    assert "UNPARSEABLE batch-00-deep.json: RecursionError" in \
        (qm_env / "quality-report.txt").read_text(encoding="utf-8")

    c = config.cfg()
    assert pipeline.weekly(c, Workspace.from_config(c), fake_embed).status == pipeline.EXIT_OK
    assert "=== done." in (qm_env / "weekly.log").read_text(encoding="utf-8")


def test_weekly_logs_any_assemble_failure(qm_env, monkeypatch):
    def boom(ws):
        raise TypeError("unexpected")

    monkeypatch.setattr(pipeline, "assemble", boom)
    c = config.cfg()
    assert pipeline.weekly(c, Workspace.from_config(c), fake_embed).status == pipeline.EXIT_FAILED
    assert "FATAL: assemble failed: TypeError: unexpected" in \
        (qm_env / "weekly.log").read_text(encoding="utf-8")


# --- the index pair ---------------------------------------------------------------------

def test_vectors_and_meta_from_two_builds_are_stale(qm_env, capsys, monkeypatch):
    cli.assemble_main([])
    assert cli.build_index_main([], embed=fake_embed) == 0
    real = Workspace.write_json

    def no_meta(self, name, obj, indent=2):
        if name == workspace.INDEX_META:
            raise OSError("disk full")
        return real(self, name, obj, indent)

    monkeypatch.setattr(Workspace, "write_json", no_meta)
    assert cli.build_index_main([], embed=fake_embed) == 1  # new vectors, old meta
    monkeypatch.setattr(Workspace, "write_json", real)
    capsys.readouterr()
    rc, out = _query(capsys, fake_embed, "need")
    assert rc == cli.EXIT_INDEX_STALE and "different index builds" in out.err


def test_an_index_from_before_build_ids_still_answers(qm_env, capsys):
    import numpy as np
    cli.assemble_main([])
    assert cli.build_index_main([], embed=fake_embed) == 0
    vec_path = str(qm_env / workspace.INDEX_VECTORS)
    with np.load(vec_path) as z:
        vecs = z["vecs"]
    np.savez(vec_path, vecs=vecs)
    meta = json.loads((qm_env / workspace.INDEX_META).read_text(encoding="utf-8"))
    del meta["build"]
    write_json(qm_env / workspace.INDEX_META, meta)
    capsys.readouterr()
    rc, _ = _query(capsys, fake_embed, "need")
    assert rc == cli.EXIT_OK


# --- --explain --------------------------------------------------------------------------

def test_explain_binds_the_exact_label_not_lookalikes(qm_env, capsys):
    lookalikes = [{"id": f"aaa-tools-superpowers-brainstorming-{n:02d}", "kind": "skill",
                   "name": f"aaa-tools:superpowers:brainstorming-{n:02d}", "what": "LOOKALIKE",
                   "use_when": "u", "avoid_when": "a", "tier": "lite"} for n in range(1, 11)]
    real = {"id": "superpowers-brainstorming", "kind": "skill", "name": "superpowers:brainstorming",
            "what": "REAL", "use_when": "u", "avoid_when": "a", "tier": "catalog"}
    write_json(qm_env / "entries" / "batch-00-lookalikes.json", lookalikes + [real])
    cli.assemble_main([])
    capsys.readouterr()
    for ref in ("superpowers:brainstorming", "/superpowers:brainstorming",
                "Superpowers:Brainstorming", "superpowers-brainstorming"):
        rc, out = _query(capsys, fake_embed, "--explain", ref)
        assert rc == 0 and "REAL" in out.out and "LOOKALIKE" not in out.out
    rc, out = _query(capsys, fake_embed, "--explain", "superpowers:brainstorm")
    assert "NO EXACT MATCH" in out.out and "and 1 more" in out.out
    assert "REAL" not in out.out and "LOOKALIKE" not in out.out
    rc, _ = _query(capsys, fake_embed, "--explain", " ")
    assert rc == cli.EXIT_USAGE


def test_explain_never_presents_a_lookalike_as_the_tool(qm_env, capsys):
    write_json(qm_env / "entries" / "batch-00-lookalike.json", [
        {"id": "aaa-tools-superpowers-brainstorming-pro", "kind": "skill",
         "name": "aaa-tools:superpowers:brainstorming-pro", "what": "LOOKALIKE",
         "use_when": "u", "avoid_when": "a", "tier": "lite"}])
    cli.assemble_main([])
    capsys.readouterr()
    rc, out = _query(capsys, fake_embed, "--explain", "superpowers:brainstorming")
    assert rc == 0 and "NO EXACT MATCH" in out.out and "LOOKALIKE" not in out.out


# --- plugin skill paths -----------------------------------------------------------------

def test_declared_skill_paths_stay_inside_the_plugin(qm_env, tmp_path, capsys):
    home = _fake_claude_home(tmp_path)
    root = tmp_path / "claude" / "plugins" / "cache" / "mkt" / "kit" / "1.0.0"
    _skill_md(tmp_path / "outside" / "far", "far", "not part of the plugin")
    _skill_md(root / "skills" / "good", "good", "declared")
    _plugin(root, "kit", {"name": "kit", "skills": [
        "../../../../../../outside", str(tmp_path / "outside"), "//host/share",
        "./skills\x00x", "./*", "./skills/good"]})
    _only(home, "kit@mkt", root)
    _configure_scan(home, [])
    capsys.readouterr()
    assert _enumerated_skills(qm_env) == [("kit:good", "declared")]
    assert capsys.readouterr().err.count("must stay inside the plugin") == 4


def test_a_skill_folder_linking_out_of_the_plugin_is_skipped(qm_env, tmp_path, capsys):
    home = _fake_claude_home(tmp_path)
    root = tmp_path / "claude" / "plugins" / "cache" / "mkt" / "plain" / "1.0.0"
    _plugin(root, "plain", {"name": "plain"})
    _skill_md(root / "skills" / "one", "one", "inside")
    _skill_md(tmp_path / "elsewhere" / "far", "far", "outside")
    try:
        os.symlink(tmp_path / "elsewhere" / "far", root / "skills" / "far", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this OS or account can't make symlinks")
    _only(home, "plain@mkt", root)
    _configure_scan(home, [])
    capsys.readouterr()
    assert [i for i, _ in _enumerated_skills(qm_env)] == ["plain:one"]
    assert "resolves outside the plugin" in capsys.readouterr().err


# --- names UTF-8 can't hold -------------------------------------------------------------

def test_an_unencodable_scan_string_costs_one_item_not_the_refresh(qm_env, monkeypatch, capsys):
    body = '{"models": [{"name": "\\ud800"}, {"name": "llama3:8b"}]}'
    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(inventory.urllib.request, "urlopen",
                        lambda url, timeout=None: _FakeResponse(body))
    config.cfg()["scan"]["ollama_models"] = True
    assert cli.enumerate_main([]) == 0
    data = json.loads((qm_env / "arsenal_items.json").read_text(encoding="utf-8"))
    assert [i["name"] for i in data["items"] if i["kind"] == "model"] == ["llama3:8b"]
    assert "not valid Unicode" in capsys.readouterr().err
    c = config.cfg()
    assert pipeline.regen(c, Workspace.from_config(c)).status == pipeline.EXIT_OK


@pytest.mark.skipif(os.name != "posix" or sys.platform == "darwin",
                    reason="needs a file system that keeps undecodable bytes in names")
def test_an_undecodable_skill_folder_name_is_skipped(qm_env, tmp_path):
    root = os.fsencode(str(tmp_path / "skills"))
    os.makedirs(root + b"/\xff")
    with open(root + b"/\xff/SKILL.md", "wb") as f:
        f.write(b"---\ndescription: d\n---\n")
    config.cfg()["scan"]["skill_roots"] = [str(tmp_path / "skills")]
    assert cli.enumerate_main([]) == 0
    data = json.loads((qm_env / "arsenal_items.json").read_text(encoding="utf-8"))
    assert [i for i in data["items"] if i["kind"] == "skill"] == []
