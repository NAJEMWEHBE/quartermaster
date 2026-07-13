# -*- coding: utf-8 -*-
import json

import assemble_catalog


def _load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_assemble_produces_consistent_catalog(qm_env):
    assemble_catalog.main()
    cat = json.loads(_load(qm_env / "arsenal.json"))

    # header is internally consistent (count == items == sum of each breakdown)
    assert cat["count"] == len(cat["items"])
    assert cat["count"] == sum(cat["by_tier"].values())
    assert cat["count"] == sum(cat["by_kind"].values())

    ids = [i["id"] for i in cat["items"]]
    # dup id "foo" collapses to one; first-loaded (deep) entry wins over the stub/dup
    assert ids.count("foo") == 1
    foo = next(i for i in cat["items"] if i["id"] == "foo")
    assert foo["what"] == "does foo"  # batch-01 deep entry, not "dup that loses"
    # id fallback: "Baz (plugin)" with no id -> slug(name)
    assert "baz-plugin" in ids
    # malformed non-dict entries were skipped, valid ones survived
    assert "second" in ids
    assert cat["by_kind"] == {"skill": 4, "plugin": 1, "model": 1, "agent": 1}
    assert cat["by_tier"] == {"route": 3, "catalog": 3, "lite": 1}


def test_assemble_quality_checks_fire(qm_env):
    assemble_catalog.main()
    report = _load(qm_env / "quality-report.txt")
    assert "missingfields: missing" in report
    assert "route-noptn: tier=route but NO route_patterns" in report
    assert "nonascii: NON-ASCII route pattern" in report
    assert "foo (dup in" in report  # dup reported


def test_assemble_md_uses_live_field_order(qm_env):
    assemble_catalog.main()
    md = _load(qm_env / "ARSENAL.md")
    # the deliberate behavior alignment: Pairs with now precedes Example (live order)
    assert "- **Pairs with:** bar\n- **Example:** foo the widget" in md
    assert md.startswith("# Your Arsenal - what you have and when to use it")
