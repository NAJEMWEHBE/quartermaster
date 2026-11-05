# -*- coding: utf-8 -*-
import json
import subprocess

import pytest

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


def _mkskill(path, name):
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: d\n---\n", encoding="utf-8")
    return str(path / "SKILL.md")


def _registry(tmp_path, *locations):
    p = tmp_path / "known_marketplaces.json"
    p.write_text(json.dumps({f"m{i}": {"installLocation": str(loc)}
                             for i, loc in enumerate(locations)}), encoding="utf-8")
    return str(p)


def test_registry_gate_drops_orphan_marketplace_clones(tmp_path):
    """An unregistered dir sitting beside registered marketplaces (a leftover temp_*
    clone) must not be enumerated; registered siblings and paths outside the
    marketplaces parent are untouched. Guards the 2026-07-19 temp_* sweep."""
    mkts = tmp_path / "marketplaces"
    good = _mkskill(mkts / "registered-mkt" / "skills" / "good", "good")
    orphan = _mkskill(mkts / "temp_1783969352387" / "skills" / "react-doctor", "react-doctor")
    outside = _mkskill(tmp_path / "cache" / "plug" / "skills" / "cached", "cached")

    keep = enumerate_arsenal.registry_gate(_registry(tmp_path, mkts / "registered-mkt"))
    assert keep(good) is True
    assert keep(orphan) is False      # under the marketplaces parent, not registered
    assert keep(outside) is True      # different tree entirely - never gated


def test_registry_gate_is_noop_without_a_readable_registry(tmp_path):
    """Fail-open: a missing/garbage/empty registry must never silently empty the scan -
    an enumeration collapse is exactly the failure this whole subsystem guards against."""
    orphan = _mkskill(tmp_path / "marketplaces" / "temp_x" / "skills" / "s", "s")
    assert enumerate_arsenal.registry_gate(str(tmp_path / "missing.json"))(orphan) is True
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert enumerate_arsenal.registry_gate(str(bad))(orphan) is True
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert enumerate_arsenal.registry_gate(str(empty))(orphan) is True


def test_registry_gate_never_gates_a_tree_outside_the_marketplaces_dir(tmp_path):
    """A directory-source marketplace can be registered from ANYWHERE on disk, so the
    gated zone must be the marketplaces dir beside the registry - not the parent of each
    installLocation. The live registry has an entry pointing at F:\\ai\\mcp-wrappers;
    parent-inference made F:\\ai a gate zone, so every skill in a sibling project there
    dropped out of LIVE and became prune bait on the next weekly run."""
    mkts = tmp_path / "marketplaces"
    registered = _mkskill(mkts / "registered-mkt" / "skills" / "good", "good")
    projects = tmp_path / "projects"
    far_mkt = _mkskill(projects / "mcp-wrappers" / "skills" / "wrapped", "wrapped")
    sibling = _mkskill(projects / "some-repo" / "skills" / "mine", "mine")

    keep = enumerate_arsenal.registry_gate(
        _registry(tmp_path, mkts / "registered-mkt", projects / "mcp-wrappers"))
    assert keep(registered) is True
    assert keep(far_mkt) is True
    assert keep(sibling) is True      # the regression: parent-inference gated this out


def test_registry_gate_fails_open_on_every_malformed_registry_shape(tmp_path):
    """The fail-open promise has to hold for shapes json.load PARSES but the gate cannot
    use. Each of these once escaped the except clause and killed enumerate main() outright,
    leaving the weekly run with no arsenal_items.json at all."""
    orphan = _mkskill(tmp_path / "marketplaces" / "temp_x" / "skills" / "s", "s")
    reg = tmp_path / "r.json"
    for body in ('[{"installLocation": "x"}]', "null", '"hello"', "42"):
        reg.write_text(body, encoding="utf-8")
        assert enumerate_arsenal.registry_gate(str(reg))(orphan) is True, body
    # right shape, unusable entries: non-str location, no location, non-dict value
    reg.write_text(json.dumps({"a": {"installLocation": 123}, "b": {}, "c": None}),
                   encoding="utf-8")
    assert enumerate_arsenal.registry_gate(str(reg))(orphan) is True
    # a perfectly valid registry written in an encoding we cannot read
    utf16 = tmp_path / "utf16.json"
    utf16.write_bytes(json.dumps({"m": {"installLocation": "x"}}).encode("utf-16"))
    assert enumerate_arsenal.registry_gate(str(utf16))(orphan) is True


def test_registry_gate_announces_when_it_turns_itself_off(tmp_path, capsys):
    """A silently-off gate re-admits orphans and the next harness cleanup of them reads
    as a real uninstall - the collapse this whole subsystem guards against."""
    enumerate_arsenal.registry_gate(str(tmp_path / "missing.json"))
    assert "orphan gate OFF" in capsys.readouterr().err


def test_find_skills_applies_the_keep_predicate(tmp_path):
    mkts = tmp_path / "marketplaces"
    _mkskill(mkts / "registered-mkt" / "skills" / "good", "good")
    _mkskill(mkts / "temp_1783969352387" / "skills" / "react-doctor", "react-doctor")
    keep = enumerate_arsenal.registry_gate(_registry(tmp_path, mkts / "registered-mkt"))
    names = {s["name"] for s in enumerate_arsenal.find_skills([str(mkts)], keep)}
    assert names == {"good"}
    # no predicate -> the orphan comes back, proving the gate is what removed it
    assert "react-doctor" in {s["name"] for s in enumerate_arsenal.find_skills([str(mkts)])}


def test_enumerate_gates_orphans_when_registry_configured(qm_env, tmp_path):
    mkts = tmp_path / "marketplaces"
    _mkskill(mkts / "registered-mkt" / "skills" / "good", "good")
    _mkskill(mkts / "temp_1783969352387" / "skills" / "react-doctor", "react-doctor")
    config.cfg()["scan"]["skill_roots"] = [str(mkts)]
    config.cfg()["scan"]["marketplaces_registry"] = _registry(tmp_path, mkts / "registered-mkt")
    enumerate_arsenal.main()
    data = json.loads((qm_env / "arsenal_items.json").read_text(encoding="utf-8"))
    assert {s["name"] for s in data["items"]} == {"good"}


def test_enumerate_includes_mcp_when_configured(qm_env):
    mcpdir = qm_env / "mcp"
    (mcpdir / "srv").mkdir(parents=True)
    config.cfg()["scan"]["mcp_dir"] = str(mcpdir)  # cfg() returns the cached dict
    enumerate_arsenal.main()
    data = json.loads((qm_env / "arsenal_items.json").read_text(encoding="utf-8"))
    assert {"kind": "mcp", "name": "srv", "scope": "local"} in data["items"]
    assert data["counts"].get("mcp") == 1


def _fm(tmp_path, body):
    p = tmp_path / "SKILL.md"
    p.write_text("---\n" + body + "---\n\n# Title\n", encoding="utf-8")
    return enumerate_arsenal.frontmatter(str(p))


def test_frontmatter_reads_yaml_block_scalars(tmp_path):
    """Block scalars are common in SKILL.md files; the parser used to return the
    indicator itself ("|-") as the description, which then became the stub text."""
    assert _fm(tmp_path, "name: lit\ndescription: |-\n  Line one.\n  Line two.\n") == \
        ("lit", "Line one.\nLine two.")
    assert _fm(tmp_path, "name: fold\ndescription: >\n  Folded one\n  folded two.\n\nlicense: MIT\n") == \
        ("fold", "Folded one folded two.")
    assert _fm(tmp_path, "description: |\n    Deep indent\n      keeps relative indent\nname: after\n") == \
        ("after", "Deep indent\n  keeps relative indent")


def test_frontmatter_reads_multi_line_plain_and_quoted_scalars(tmp_path):
    assert _fm(tmp_path, "name: plain\ndescription: Starts here\n  and continues.\n") == \
        ("plain", "Starts here and continues.")
    assert _fm(tmp_path, 'name: "q"\ndescription: "Quoted, with: colon\n  over two lines"\n') == \
        ("q", "Quoted, with: colon over two lines")
    assert _fm(tmp_path, "name: s\ndescription: 'It''s single'\n") == ("s", "It's single")
    assert _fm(tmp_path, "name: plain-one\ndescription: just one line\n") == ("plain-one", "just one line")


class _FakeResponse:
    def __init__(self, body):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _no_subprocess(*a, **k):
    raise AssertionError("must not shell out: `ollama list` auto-starts the Ollama app on Windows")


def test_ollama_models_asks_the_running_server_and_never_starts_ollama(monkeypatch):
    seen = {}

    def fake_urlopen(url, timeout=None):
        seen["url"], seen["timeout"] = url, timeout
        return _FakeResponse('{"models": [{"name": "qwen3-embedding:0.6b"}, {"name": "llama3:8b"}]}')

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _no_subprocess)
    monkeypatch.setattr(enumerate_arsenal.urllib.request, "urlopen", fake_urlopen)
    models = enumerate_arsenal.ollama_models("http://127.0.0.1:11434/")
    assert [m["name"] for m in models] == ["qwen3-embedding:0.6b", "llama3:8b"]
    assert all(m["kind"] == "model" for m in models)
    assert seen["url"] == "http://127.0.0.1:11434/api/tags"
    assert seen["timeout"] <= 5


def test_ollama_models_warns_and_skips_when_the_server_is_down(monkeypatch, capsys):
    def refused(url, timeout=None):
        raise enumerate_arsenal.urllib.error.URLError("connection refused")

    monkeypatch.setattr(subprocess, "run", _no_subprocess)
    monkeypatch.setattr(enumerate_arsenal.urllib.request, "urlopen", refused)
    assert enumerate_arsenal.ollama_models("http://127.0.0.1:11434") == []
    assert "WARNING" in capsys.readouterr().err


def _skill_md(path, name, desc):
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\n---\n", encoding="utf-8")


def _fake_claude_home(tmp_path):
    """A ~/.claude-shaped tree: the plugin cache keeps an old version dir, two plugins
    ship a skill with the same name, one plugin is installed but disabled, and the
    marketplace clone carries a plugin that is not installed at all."""
    home = tmp_path / "claude"
    plugins = home / "plugins"
    cache = plugins / "cache" / "mkt"
    _skill_md(cache / "alpha" / "1.0.0" / "skills" / "tdd", "tdd", "old version")
    _skill_md(cache / "alpha" / "1.1.0" / "skills" / "tdd", "tdd", "live version")
    _skill_md(cache / "beta" / "1.0.0" / "skills" / "access", "access", "beta access")
    _skill_md(cache / "gamma" / "2.0.0" / "skills" / "nested" / "access", "access", "gamma access")
    _skill_md(cache / "off" / "1.0.0" / "skills" / "offskill", "offskill", "disabled plugin")
    _skill_md(plugins / "marketplaces" / "mkt" / "plugins" / "ghost" / "skills" / "ghost",
              "ghost", "plugin that is not installed")
    _skill_md(home / "skills" / "mine", "mine", "a user skill")

    def rec(plugin, version):
        return [{"scope": "user", "installPath": str(cache / plugin / version), "version": version}]

    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "alpha@mkt": rec("alpha", "1.1.0"), "beta@mkt": rec("beta", "1.0.0"),
        "gamma@mkt": rec("gamma", "2.0.0"), "off@mkt": rec("off", "1.0.0")}}), encoding="utf-8")
    (home / "settings.json").write_text(json.dumps({"enabledPlugins": {
        "alpha@mkt": True, "beta@mkt": True, "gamma@mkt": True, "off@mkt": False}}), encoding="utf-8")
    return home


def _configure_scan(home, skill_roots):
    scan = config.cfg()["scan"]
    scan["skill_roots"] = skill_roots
    scan["installed_plugins"] = str(home / "plugins" / "installed_plugins.json")
    scan["claude_settings"] = str(home / "settings.json")
    scan["marketplaces_registry"] = None


def _enumerated_skills(qm_env):
    enumerate_arsenal.main()
    data = json.loads((qm_env / "arsenal_items.json").read_text(encoding="utf-8"))
    return sorted((s["invoke"], s["desc"]) for s in data["items"] if s["kind"] == "skill")


def test_plugin_skills_come_from_the_live_install_of_each_enabled_plugin(qm_env, tmp_path):
    home = _fake_claude_home(tmp_path)
    _configure_scan(home, [str(home / "skills")])
    assert _enumerated_skills(qm_env) == [
        ("alpha:tdd", "live version"),     # not the stale 1.0.0 dir the cache still holds
        ("beta:access", "beta access"),    # two plugins' `access` skills stay two tools
        ("gamma:access", "gamma access"),
        ("mine", "a user skill"),          # user skills keep their bare name
    ]                                      # no `offskill` (disabled), no `ghost` (not installed)


def test_legacy_plugin_scan_roots_are_skipped_once_installed_plugins_is_set(qm_env, tmp_path, capsys):
    """Old configs list plugins/cache and plugins/marketplaces as skill roots; walking them
    would bring back every stale version and uninstalled plugin."""
    home = _fake_claude_home(tmp_path)
    plugins = home / "plugins"
    _configure_scan(home, [str(home / "skills"), str(plugins / "cache"), str(plugins / "marketplaces")])
    assert [i for i, _ in _enumerated_skills(qm_env)] == ["alpha:tdd", "beta:access", "gamma:access", "mine"]
    assert "skipping skill root" in capsys.readouterr().err


def test_unreadable_installed_plugins_fails_loudly(qm_env, tmp_path):
    """A garbled plugin registry must stop the run, not quietly drop every plugin skill
    (which the next --prune would read as a mass uninstall)."""
    home = _fake_claude_home(tmp_path)
    (home / "plugins" / "installed_plugins.json").write_text("{not json", encoding="utf-8")
    _configure_scan(home, [str(home / "skills")])
    with pytest.raises(SystemExit) as exc:
        enumerate_arsenal.main()
    assert exc.value.code not in (0, None)
