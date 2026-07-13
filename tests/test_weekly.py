# -*- coding: utf-8 -*-
from entry import Entry
import weekly


def test_new_tool_becomes_a_stub():
    added = [{"name": "New Tool", "kind": "skill", "desc": "does new things"}]
    kept = weekly.stub_queue(added, old_stubs=[], deep_keys=set(), live_keys={"new-tool"})
    assert [e.id for e in kept] == ["new-tool"]
    assert kept[0].what.endswith("[STUB - not yet deep-studied]")


def test_stub_retires_when_deep_entry_appears():
    added = [{"name": "New Tool", "kind": "skill", "desc": "d"}]
    # a deep entry now covers the key -> stub drops out of the queue
    kept = weekly.stub_queue(added, old_stubs=[], deep_keys={"new-tool"}, live_keys={"new-tool"})
    assert kept == []


def test_stub_retires_when_uninstalled():
    old = [Entry.make_stub({"name": "Gone", "kind": "skill", "desc": "d"})]
    # still installed -> kept
    assert [e.id for e in weekly.stub_queue([], old, set(), {"gone"})] == ["gone"]
    # uninstalled (not in live_keys) -> retired
    assert weekly.stub_queue([], old, set(), set()) == []


def test_existing_stub_wins_over_new_for_same_key():
    old = [Entry.make_stub({"name": "Dup", "kind": "skill", "desc": "old desc"})]
    added = [{"name": "Dup", "kind": "skill", "desc": "new desc"}]
    kept = weekly.stub_queue(added, old, set(), {"dup"})
    assert len(kept) == 1
    assert "old desc" in kept[0].what  # setdefault keeps the existing stub
