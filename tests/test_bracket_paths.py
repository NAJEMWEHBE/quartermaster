# -*- coding: utf-8 -*-
"""Folder names with glob metacharacters ([ ] * ?) must be matched literally:
a work dir or skill root named "Jo [Work]" used to find no files at all."""
import json

from conftest import BATCH_01, BATCH_02, BATCH_ZZ_STUBS, write_json
from quartermaster import cli, inventory, pipeline, workspace

BRACKETS = "Jo [Work]"


def _bracket_env(tmp_path, monkeypatch):
    work = tmp_path / BRACKETS / "work"
    entries = work / "entries"
    entries.mkdir(parents=True)
    write_json(entries / "batch-01-core.json", BATCH_01)
    write_json(entries / "batch-02-more.json", BATCH_02)
    write_json(entries / "batch-zz-stubs.json", BATCH_ZZ_STUBS)
    cfg_path = tmp_path / "quartermaster.config.json"
    write_json(cfg_path, {
        "work_dir": str(work), "log_file": "weekly.log", "copy_to": None,
        "embed": {"provider": "ollama", "url": "http://127.0.0.1:11434",
                  "model": "qwen3-embedding:0.6b"},
        "query": {"min_sim": 0.60},
        "scan": {"skill_roots": [], "agents_dir": None, "claude_settings": None,
                 "marketplaces_registry": None, "mcp_dir": None, "ollama_models": False},
    })
    monkeypatch.setenv("QUARTERMASTER_CONFIG", str(cfg_path))
    return work


def test_load_batches_in_a_bracketed_work_dir(tmp_path, monkeypatch):
    ws = workspace.Workspace(_bracket_env(tmp_path, monkeypatch))
    _, _, nfiles = pipeline.load_batches(ws)
    assert nfiles == 3


def test_assemble_in_a_bracketed_work_dir_builds_the_full_catalog(tmp_path, monkeypatch):
    work = _bracket_env(tmp_path, monkeypatch)
    cli.assemble_main([])
    with open(work / "arsenal.json", encoding="utf-8") as f:
        cat = json.load(f)
    assert cat["count"] == 7  # same as the plain-folder fixture in test_assemble.py


def test_deep_entries_in_a_bracketed_work_dir(tmp_path, monkeypatch):
    ws = workspace.Workspace(_bracket_env(tmp_path, monkeypatch))
    ids = {e.id for e in pipeline._deep_entries(ws)}
    assert {"foo", "second"} <= ids


def test_find_skills_under_a_bracketed_root(tmp_path):
    skill = tmp_path / BRACKETS / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: alpha\ndescription: d\n---\n", encoding="utf-8")
    names = {s["name"] for s in inventory.find_skills([str(tmp_path / BRACKETS / "skills")])}
    assert names == {"alpha"}
