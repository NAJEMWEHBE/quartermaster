# -*- coding: utf-8 -*-
"""A failed index rebuild must surface as a failure, not a successful run with a
stale index. The embed URL points at a closed local port, so nothing is contacted."""
import json
import sys

import assemble_catalog
import config
import regen_arsenal
import weekly

DEAD_EMBEDDER = "http://127.0.0.1:9"  # discard port: connection refused at once


def _dead_embedder(qm_env):
    cfg_path = config.CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as f:
        c = json.load(f)
    c["embed"]["url"] = DEAD_EMBEDDER
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(c, f)  # the scripts regen/weekly start read this file
    config._cfg = None


def test_regen_exits_nonzero_when_the_index_build_fails(qm_env, monkeypatch, capsys):
    _dead_embedder(qm_env)
    assemble_catalog.main()
    monkeypatch.setattr(sys, "argv", ["regen_arsenal.py", "--rebuild-index"])
    assert regen_arsenal.main() == regen_arsenal.EXIT_INDEX_FAILED
    assert "build_index.py: FAILED" in capsys.readouterr().out


def test_weekly_logs_index_stale_and_fails_when_the_index_build_fails(qm_env):
    _dead_embedder(qm_env)
    rc = weekly.main()
    log = (qm_env / "weekly.log").read_text(encoding="utf-8")
    assert rc == regen_arsenal.EXIT_INDEX_FAILED
    assert "INDEX STALE" in log
    assert "=== done." in log  # the catalog itself was still rebuilt and logged
