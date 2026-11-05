# -*- coding: utf-8 -*-
from entry import Entry
import weekly

NEW_TOOL = {"name": "New Tool", "kind": "skill", "desc": "does new things"}


def test_new_tool_becomes_a_stub():
    kept = weekly.stub_queue([NEW_TOOL], old_stubs=[], deep_keys=set(), live=[NEW_TOOL])
    assert [e.id for e in kept] == ["new-tool"]
    assert kept[0].what.endswith("[STUB - not yet deep-studied]")


def test_stub_retires_when_deep_entry_appears():
    # a deep entry now covers the key -> stub drops out of the queue
    kept = weekly.stub_queue([NEW_TOOL], old_stubs=[], deep_keys={("skill", "new-tool")},
                             live=[NEW_TOOL])
    assert kept == []


def test_stub_retires_when_uninstalled():
    gone = {"name": "Gone", "kind": "skill", "desc": "d"}
    old = [Entry.make_stub(gone)]
    # still installed -> kept
    assert [e.id for e in weekly.stub_queue([], old, set(), [gone])] == ["gone"]
    # uninstalled (not live any more) -> retired
    assert weekly.stub_queue([], old, set(), []) == []


def test_existing_stub_wins_over_new_for_same_key():
    old = [Entry.make_stub({"name": "Dup", "kind": "skill", "desc": "old desc"})]
    added = [{"name": "Dup", "kind": "skill", "desc": "new desc"}]
    kept = weekly.stub_queue(added, old, set(), added)
    assert len(kept) == 1
    assert "old desc" in kept[0].what  # setdefault keeps the existing stub


def test_same_named_plugin_skills_get_one_stub_each():
    live = [{"kind": "skill", "name": "access", "invoke": f"{p}:access", "desc": p}
            for p in ("beta", "gamma")]
    kept = weekly.stub_queue(live, [], set(), live)
    assert [(e.id, e.name) for e in kept] == [("beta-access", "beta:access"),
                                             ("gamma-access", "gamma:access")]


def test_a_deep_entry_under_the_bare_name_retires_a_unique_plugin_skill_stub():
    tdd = {"kind": "skill", "name": "tdd", "invoke": "mattpocock-skills:tdd", "desc": "d"}
    stub = Entry.make_stub(tdd)
    assert weekly.stub_queue([], [stub], {("skill", "tdd")}, [tdd]) == []


def test_a_plugin_entry_does_not_retire_the_stub_of_a_skill_with_its_name():
    foo = {"kind": "skill", "name": "foo", "desc": "d"}
    kept = weekly.stub_queue([foo], [], {("plugin", "foo")}, [foo, {"kind": "plugin", "name": "foo"}])
    assert [e.id for e in kept] == ["foo"]
