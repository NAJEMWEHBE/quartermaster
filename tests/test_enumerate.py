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
