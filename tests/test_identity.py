# -*- coding: utf-8 -*-
"""Tool identity across the diff, the stubs and the catalog: plugin skills are
`plugin:skill`, and a plugin and a skill that share a name are two tools."""
from entry import Entry
import regen_arsenal


def skill(name, plugin=None):
    it = {"kind": "skill", "name": name, "invoke": f"{plugin}:{name}" if plugin else name}
    if plugin:
        it["plugin"] = plugin
    return it


def studied(id_, kind="skill", name=None):
    return {"id": id_, "kind": kind, "name": name or id_}


def names(items):
    return sorted(i.get("invoke") or i.get("id") for i in items)


def test_same_named_skills_from_two_plugins_are_both_new():
    live = [skill("access", "beta"), skill("access", "gamma")]
    added, removed, unchanged = regen_arsenal.diff(live, [])
    assert names(added) == ["beta:access", "gamma:access"]


def test_a_legacy_entry_keyed_by_bare_name_still_matches_a_unique_plugin_skill():
    """Catalogs studied before plugin:skill identity use the bare skill name as id."""
    added, removed, unchanged = regen_arsenal.diff([skill("tdd", "mattpocock-skills")],
                                                   [studied("tdd")])
    assert (added, removed, unchanged) == ([], [], 1)


def test_a_bare_name_shared_by_two_live_skills_identifies_neither():
    legacy = studied("access")
    added, removed, unchanged = regen_arsenal.diff([skill("access", "beta"), skill("access", "gamma")],
                                                   [legacy])
    assert names(added) == ["beta:access", "gamma:access"]
    assert removed == [legacy]


def test_entries_named_by_invoke_match_their_plugin_skill():
    live = [skill("access", "beta"), skill("access", "gamma")]
    cat = [studied("beta-access", name="beta:access"), studied("gamma-access", name="gamma:access")]
    assert regen_arsenal.diff(live, cat) == ([], [], 2)


def test_a_plugin_and_a_skill_with_the_same_name_are_two_tools():
    live = [{"kind": "plugin", "name": "foo"}, skill("foo")]
    added, removed, unchanged = regen_arsenal.diff(live, [studied("foo", kind="skill")])
    assert [(a["kind"], a["name"]) for a in added] == [("plugin", "foo")]
    assert removed == []


def test_models_still_match_fuzzily_and_are_never_reported_new_twice():
    live = [{"kind": "model", "name": "qwen3-embedding:0.6b"}]
    assert regen_arsenal.diff(live, [studied("qwen3-embedding", kind="model")]) == ([], [], 1)


def test_stub_for_a_plugin_skill_is_named_by_its_invoke_name():
    s = Entry.make_stub({"kind": "skill", "name": "access", "invoke": "beta:access", "desc": "d"})
    assert (s.id, s.name) == ("beta-access", "beta:access")


def test_an_entry_without_a_kind_matches_any_kind():
    """Hand-written or legacy entries may lack `kind`; they must not be pruned for it."""
    entry = {"id": "foo", "name": "Foo"}
    assert regen_arsenal.diff([skill("foo")], [entry]) == ([], [], 1)
