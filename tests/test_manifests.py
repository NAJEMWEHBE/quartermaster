# -*- coding: utf-8 -*-
"""The plugin manifests agree with each other and with the files they point at."""
import json
import os

from quartermaster import __version__

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return json.load(f)


def test_the_marketplace_lists_the_plugin_at_its_real_source():
    market = _json(".claude-plugin", "marketplace.json")
    [entry] = market["plugins"]
    plugin_dir = os.path.normpath(os.path.join(ROOT, entry["source"]))
    plugin = _json(os.path.relpath(plugin_dir, ROOT), ".claude-plugin", "plugin.json")
    assert entry["name"] == plugin["name"] == "quartermaster"


def test_the_version_is_declared_once():
    """Only plugin.json's version counts; copies elsewhere drift."""
    market = _json(".claude-plugin", "marketplace.json")
    assert "version" not in market and all("version" not in p for p in market["plugins"])
    assert _json(".claude-plugin", "plugin.json")["version"] == __version__


def test_every_declared_skill_exists_and_names_itself():
    plugin = _json(".claude-plugin", "plugin.json")
    for path in plugin["skills"]:
        skill_md = os.path.join(ROOT, path, "SKILL.md")
        with open(skill_md, encoding="utf-8") as f:
            head = f.read(400)
        assert head.startswith("---\n") and f"name: {os.path.basename(path)}\n" in head


def test_the_skill_runs_the_bundled_engine():
    with open(os.path.join(ROOT, "skills", "arsenal", "SKILL.md"), encoding="utf-8") as f:
        body = f.read()
    for script in ("query_arsenal.py", "weekly.py"):
        assert f'"${{CLAUDE_PLUGIN_ROOT}}/{script}"' in body
        assert os.path.isfile(os.path.join(ROOT, script))
