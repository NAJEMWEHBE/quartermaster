# -*- coding: utf-8 -*-
import json

import config
import enumerate_arsenal


def test_local_mcp_config_driven(tmp_path):
    assert enumerate_arsenal.local_mcp(None) == []
    assert enumerate_arsenal.local_mcp("") == []
    (tmp_path / "server-a").mkdir()
    (tmp_path / "server-b").mkdir()
    (tmp_path / "loose.txt").write_text("x", encoding="utf-8")  # files ignored
    assert enumerate_arsenal.local_mcp(str(tmp_path)) == [
        {"kind": "mcp", "name": "server-a", "scope": "local"},
        {"kind": "mcp", "name": "server-b", "scope": "local"},
    ]


def test_enumerate_includes_mcp_when_configured(qm_env):
    mcpdir = qm_env / "mcp"
    (mcpdir / "srv").mkdir(parents=True)
    config.cfg()["scan"]["mcp_dir"] = str(mcpdir)  # cfg() returns the cached dict
    enumerate_arsenal.main()
    data = json.loads((qm_env / "arsenal_items.json").read_text(encoding="utf-8"))
    assert {"kind": "mcp", "name": "srv", "scope": "local"} in data["items"]
    assert data["counts"].get("mcp") == 1
