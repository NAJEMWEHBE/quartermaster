# -*- coding: utf-8 -*-
"""Where the engine finds its config and its work dir."""
import json
import os
import subprocess
import sys

import catalog_file
from entry import Entry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_relative_work_dir_resolves_beside_the_config_not_the_cwd(tmp_path):
    """The /arsenal skill and the Task Scheduler run the scripts from any folder, so a
    relative work_dir must mean "relative to the config file"."""
    home = tmp_path / "engine"
    data = home / "data"
    data.mkdir(parents=True)
    catalog_file.write(str(data / "arsenal.json"),
                       [Entry.from_raw({"id": "foo", "kind": "skill", "name": "Foo",
                                        "what": "does foo"})])
    cfg_path = home / "quartermaster.config.json"
    cfg_path.write_text(json.dumps({"work_dir": "./data"}), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    env = dict(os.environ, QUARTERMASTER_CONFIG=str(cfg_path))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "query_arsenal.py"), "--explain", "foo"],
                       cwd=str(elsewhere), env=env, capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "does foo" in r.stdout
    assert not (elsewhere / "data").exists()
