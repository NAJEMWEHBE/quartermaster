# -*- coding: utf-8 -*-
"""A failed index rebuild must surface as a failure, not a successful run with a
stale index. The embed URL points at a closed local port, so nothing is contacted."""
import json

from quartermaster import cli, pipeline
from quartermaster import config

DEAD_EMBEDDER = "http://127.0.0.1:9"  # discard port: connection refused at once


def _dead_embedder(qm_env):
    cfg_path = config.config_path()
    with open(cfg_path, encoding="utf-8") as f:
        c = json.load(f)
    c["embed"]["url"] = DEAD_EMBEDDER
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(c, f)


def test_regen_exits_nonzero_when_the_index_build_fails(qm_env, monkeypatch, capsys):
    _dead_embedder(qm_env)
    cli.assemble_main([])
    assert cli.regen_main(["--rebuild-index"]) == pipeline.EXIT_INDEX_FAILED
    assert "build_index: FAILED" in capsys.readouterr().out


def test_weekly_logs_index_stale_and_fails_when_the_index_build_fails(qm_env):
    _dead_embedder(qm_env)
    rc = cli.weekly_main([])
    log = (qm_env / "weekly.log").read_text(encoding="utf-8")
    assert rc == pipeline.EXIT_INDEX_FAILED
    assert "INDEX STALE" in log
    assert "=== done." in log  # the catalog itself was still rebuilt and logged
