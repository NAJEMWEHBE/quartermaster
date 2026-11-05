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


def test_every_relative_path_in_the_config_resolves_beside_it(tmp_path, monkeypatch):
    import config
    cfg_path = tmp_path / "conf" / "quartermaster.config.json"
    cfg_path.parent.mkdir()
    cfg_path.write_text(json.dumps({
        "work_dir": "data", "copy_to": "../share/arsenal.json",
        "scan": {"skill_roots": ["./skills", "~/abs-ish"], "installed_plugins": "p/installed.json",
                 "claude_settings": "settings.json", "agents_dir": None, "ollama_models": False}}),
        encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", str(cfg_path))
    monkeypatch.setattr(config, "_cfg", None)
    monkeypatch.chdir(tmp_path)
    c = config.cfg()
    base = cfg_path.parent
    assert c["work_dir"] == os.path.normpath(str(base / "data"))
    assert c["copy_to"] == os.path.normpath(str(tmp_path / "share" / "arsenal.json"))
    assert c["scan"]["skill_roots"][0] == os.path.normpath(str(base / "skills"))
    assert c["scan"]["skill_roots"][1] == os.path.normpath(os.path.expanduser("~/abs-ish"))
    assert c["scan"]["installed_plugins"] == os.path.normpath(str(base / "p" / "installed.json"))
    assert c["scan"]["claude_settings"] == os.path.normpath(str(base / "settings.json"))
    assert c["scan"]["agents_dir"] is None
    config._cfg = None
