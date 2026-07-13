# -*- coding: utf-8 -*-
import entry
from entry import Entry, Tier, offline_label, embed_text, md_block, render_md


def test_tier_coercion():
    assert Tier.coerce("route") is Tier.route
    assert Tier.coerce("catalog") is Tier.catalog
    assert Tier.coerce("lite") is Tier.lite
    assert Tier.coerce("bogus") is Tier.catalog
    assert Tier.coerce("") is Tier.catalog
    assert Tier.coerce(None) is Tier.catalog
    assert Tier.coerce(Tier.lite) is Tier.lite
    # StrEnum serializes as a plain string
    assert str(Tier.route) == "route"
    assert Tier.route == "route"


def test_from_raw_list_coercion():
    e = Entry.from_raw({"id": "x", "name": "X", "pairs_with": "solo",
                        "triggers": ["a", "b"], "supersedes": None, "route_patterns": ""})
    assert e.pairs_with == ["solo"]      # scalar -> [scalar]
    assert e.triggers == ["a", "b"]      # list stays
    assert e.supersedes == []            # None -> []
    assert e.route_patterns == []        # "" -> []


def test_from_raw_scalar_defaults_and_id_fallback():
    e = Entry.from_raw({"name": "Foo Bar", "kind": "skill"})
    assert e.id == "foo-bar"             # id falls back to slug(name)
    assert e.what == "" and e.use_when == "" and e.cost == ""
    assert e.tier is Tier.catalog
    empty = Entry.from_raw({})
    assert empty.id == "unknown"         # no id, no name


def test_from_raw_tier_coerced():
    assert Entry.from_raw({"id": "a", "tier": "route"}).tier is Tier.route
    assert Entry.from_raw({"id": "a", "tier": "weird"}).tier is Tier.catalog


def test_offline_label_vocab():
    assert offline_label(True) == "offline"
    assert offline_label("partial") == "partial"
    assert offline_label(False) == "online"
    assert offline_label("") == "online"
    assert offline_label("whatever") == "online"


def test_to_dict_order_and_tier_is_str():
    e = Entry.from_raw({"id": "a", "name": "A", "tier": "route"})
    d = e.to_dict()
    assert list(d.keys()) == entry.FIELDS
    assert d["tier"] == "route" and type(d["tier"]) is str


def test_round_trip_from_dict_to_dict():
    for raw in (
        {"id": "foo", "kind": "skill", "name": "Foo", "what": "w", "use_when": "u",
         "avoid_when": "a", "offline": True, "cost": "free", "pairs_with": ["bar"],
         "triggers": ["t1", "t2"], "example": "ex", "tier": "route",
         "route_patterns": ["p1"]},
        {"id": "m", "kind": "model", "name": "m", "offline": False, "tier": "lite"},
        {"name": "No Id Here"},
    ):
        e = Entry.from_raw(raw)
        assert Entry.from_dict(e.to_dict()) == e


def test_make_stub_with_desc():
    s = Entry.make_stub({"name": "New Tool", "kind": "plugin", "desc": "A shiny new plugin for X"})
    assert s.id == "new-tool"
    assert s.kind == "plugin"
    assert s.name == "New Tool"
    assert s.what == "A shiny new plugin for X [STUB - not yet deep-studied]"
    assert s.use_when == "Possibly relevant when the need matches: A shiny new plugin for X"
    assert s.avoid_when == ("Stub entry pending deep study - details unverified; "
                            "confirm against the tool itself before relying on it.")
    assert s.offline == "" and s.cost == ""
    assert s.triggers == ["New Tool"]
    assert s.tier is Tier.lite
    assert s.route_patterns == [] and s.pairs_with == [] and s.supersedes == []


def test_make_stub_without_desc():
    s = Entry.make_stub({"name": "X", "kind": "skill"})
    assert s.what == "X (no description found) [STUB - not yet deep-studied]"
    assert s.use_when == "Unknown until studied."
    assert s.id == "x"


def test_md_block_golden():
    e = Entry.from_raw({
        "id": "foo", "kind": "skill", "name": "Foo", "what": "does foo",
        "use_when": "when you need foo", "avoid_when": "not for bar", "offline": True,
        "cost": "free-local", "pairs_with": ["bar", "baz"], "example": "foo the widget",
        "tier": "route",
    })
    expected = (
        "### Foo  `skill` - offline, free-local\n"
        "- **What:** does foo\n"
        "- **Use when:** when you need foo\n"
        "- **Avoid when:** not for bar\n"
        "- **Pairs with:** bar, baz\n"
        "- **Example:** foo the widget\n"
    )
    assert md_block(e) == expected


def test_md_block_omits_empty_fields():
    e = Entry.from_raw({"id": "x", "kind": "skill", "name": "X"})
    # only the heading and the trailing blank line survive
    assert md_block(e) == "### X  `skill` - online, \n"


def test_embed_text_template():
    e = Entry.from_raw({"id": "myid", "name": "Foo", "triggers": ["a", "b"],
                        "use_when": "u", "what": "w"})
    assert embed_text(e) == "Foo  a b  u  w"
    # name falls back to id when name is empty
    e2 = Entry.from_raw({"id": "myid", "name": "", "what": "w"})
    assert embed_text(e2) == "myid  w"


def test_render_md_document():
    e = Entry.from_raw({"id": "a", "kind": "skill", "name": "A", "what": "wa",
                        "use_when": "u", "avoid_when": "v", "tier": "catalog"})
    doc = render_md([e], "2026-01-01T00:00:00")
    assert doc.startswith("# Your Arsenal - what you have and when to use it\n")
    assert "_Auto-generated 2026-01-01T00:00:00 - 1 tools (0 core / 1 catalog / 0 long-tail)._" in doc
    assert "## Catalog (useful - ask your agent for them)" in doc
    assert doc.endswith("### A  `skill` - online, \n- **What:** wa\n- **Use when:** u\n- **Avoid when:** v\n\n")
