# -*- coding: utf-8 -*-
import catalog_file
from entry import Entry


def _sample_entries():
    return [
        Entry.from_raw({"id": "b-skill", "kind": "skill", "name": "B", "tier": "catalog"}),
        Entry.from_raw({"id": "a-route", "kind": "skill", "name": "A", "tier": "route",
                        "route_patterns": ["a"]}),
        Entry.from_raw({"id": "z-model", "kind": "model", "name": "Z", "tier": "lite"}),
        Entry.from_raw({"id": "a-plugin", "kind": "plugin", "name": "P", "tier": "catalog"}),
    ]


def test_build_header_consistent():
    items = _sample_entries()
    payload = catalog_file.build(items, generated="2026-01-01T00:00:00")
    assert payload["generated"] == "2026-01-01T00:00:00"
    assert payload["count"] == len(items)
    assert sum(payload["by_tier"].values()) == len(items)
    assert sum(payload["by_kind"].values()) == len(items)
    assert payload["by_tier"] == {"catalog": 2, "route": 1, "lite": 1}
    assert payload["by_kind"] == {"skill": 2, "model": 1, "plugin": 1}
    # tier is emitted as a plain string in every item
    assert all(type(it["tier"]) is str for it in payload["items"])


def test_build_sorts_route_first_then_kind_id():
    items = _sample_entries()
    ids = [it["id"] for it in catalog_file.build(items, generated="g")["items"]]
    # route tier first, then (kind, id) ascending: kind "model" < "plugin" < "skill"
    assert ids == ["a-route", "z-model", "a-plugin", "b-skill"]


def test_write_parse_round_trip(tmp_path):
    items = _sample_entries()
    path = tmp_path / "arsenal.json"
    catalog_file.write(str(path), items, generated="2026-01-01T00:00:00")
    header, parsed = catalog_file.parse(str(path))
    assert header["count"] == len(items)
    assert header["generated"] == "2026-01-01T00:00:00"
    expected = sorted(items, key=lambda e: (e.tier != "route", e.kind, e.id))
    assert parsed == expected
