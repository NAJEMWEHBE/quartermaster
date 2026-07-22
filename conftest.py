# -*- coding: utf-8 -*-
"""Shared pytest fixtures. Lives at the repo root so the repo root is importable
(config, entry, matching, catalog_file, and the scripts are top-level modules)."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


# The standard fixture batches: a dup id, a malformed (non-dict) entry, an entry with
# parens in its name, a model with a messy tag, tier=route with and without patterns,
# a non-ascii route pattern, a missing-fields entry, and a stub batch (zz -> loads last).
BATCH_01 = [
    {"id": "foo", "kind": "skill", "name": "Foo", "what": "does foo",
     "use_when": "when you need foo", "avoid_when": "not for bar", "offline": True,
     "cost": "free-local", "pairs_with": ["bar"], "supersedes": [],
     "triggers": ["do foo", "foo it"], "example": "foo the widget", "tier": "route",
     "route_patterns": ["foo", "do foo"]},
    {"id": "route-noptn", "kind": "skill", "name": "RouteNoPtn", "what": "x",
     "use_when": "y", "avoid_when": "z", "tier": "route", "route_patterns": []},
    {"id": "nonascii", "kind": "skill", "name": "NonAscii", "what": "x",
     "use_when": "y", "avoid_when": "z", "tier": "route", "route_patterns": ["café"]},
    {"kind": "plugin", "name": "Baz (plugin)", "what": "a baz",
     "use_when": "u", "avoid_when": "a", "tier": "catalog"},
    {"id": "mdl", "kind": "model", "name": "qwen3-embedding:0.6b", "what": "embeds text",
     "use_when": "when embedding", "avoid_when": "chat", "tier": "lite"},
    {"id": "missingfields", "kind": "skill", "name": "MissingFields", "tier": "catalog"},
]
BATCH_02 = [
    {"id": "foo", "kind": "skill", "name": "Foo Dup", "what": "dup that loses",
     "use_when": "u", "avoid_when": "a", "tier": "catalog"},
    "this is not a dict entry",
    42,
    {"id": "second", "kind": "agent", "name": "Second", "what": "second tool",
     "use_when": "u", "avoid_when": "a", "tier": "catalog"},
]
BATCH_ZZ_STUBS = [
    {"id": "foo", "kind": "skill", "name": "Foo", "what": "stub that is shadowed [STUB - not yet deep-studied]",
     "use_when": "Unknown until studied.", "avoid_when": "stub", "offline": "", "cost": "",
     "pairs_with": [], "supersedes": [], "triggers": ["Foo"], "example": "", "tier": "lite",
     "route_patterns": []},
]


@pytest.fixture
def qm_env(tmp_path, monkeypatch):
    """A configured work_dir with the standard batch files and QUARTERMASTER_CONFIG set.

    Resets config's module-level cache so cfg() reloads the test config. Yields the
    work_dir Path; tests may add/overwrite batch files under work_dir/entries.
    """
    work = tmp_path / "work"
    entries = work / "entries"
    entries.mkdir(parents=True)
    write_json(entries / "batch-01-core.json", BATCH_01)
    write_json(entries / "batch-02-more.json", BATCH_02)
    write_json(entries / "batch-zz-stubs.json", BATCH_ZZ_STUBS)

    cfg = {
        "work_dir": str(work),
        "log_file": "weekly.log",
        "copy_to": None,
        "embed": {"provider": "ollama", "url": "http://127.0.0.1:11434",
                  "model": "qwen3-embedding:0.6b"},
        "query": {"min_sim": 0.60},
        "scan": {"skill_roots": [], "agents_dir": None, "claude_settings": None,
                 "marketplaces_registry": None, "mcp_dir": None, "ollama_models": False},
    }
    cfg_path = tmp_path / "quartermaster.config.json"
    write_json(cfg_path, cfg)
    monkeypatch.setenv("QUARTERMASTER_CONFIG", str(cfg_path))

    # config.CONFIG_PATH is resolved at import time, so point it at the test config
    # directly (and clear the cache) rather than relying on the env var alone.
    import config
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(config, "_cfg", None, raising=False)
    yield work
    config._cfg = None
