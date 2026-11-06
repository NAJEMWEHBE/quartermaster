# -*- coding: utf-8 -*-
"""Owner of the catalog *Entry record* - the shape of one tool in the arsenal.

Everything about an entry lives here and nowhere else:
  - FIELDS / LIST_FIELDS   the 14-field contract and which fields are lists
  - Tier                   the tier vocabulary + coercion
  - offline_label          the single tri-state ('offline'/'partial'/'online') vocab
  - Entry.from_raw         normalize a study-fleet dict into a record (was
                           assemble_catalog.normalize)
  - Entry.make_stub        the placeholder record for a not-yet-studied tool (was
                           weekly.make_stub)
  - md_block / render_md   the ONE ARSENAL.md renderer
  - embed_text             the ONE semantic-index embedding template

Readers never re-derive any of this; they import it.
"""
import collections
from dataclasses import dataclass, field
from enum import Enum

from . import matching
from .workspace import term_safe

# The 14-field entry contract, in the exact serialization order. Byte-identity of
# arsenal.json depends on this order (dicts preserve insertion order).
FIELDS = ["id", "kind", "name", "what", "use_when", "avoid_when", "offline",
          "cost", "pairs_with", "supersedes", "triggers", "example", "tier", "route_patterns"]
LIST_FIELDS = {"pairs_with", "supersedes", "triggers", "route_patterns"}

# Ends the `what` of every placeholder entry; a tool whose entry carries it is unstudied.
STUB_MARK = "[STUB - not yet deep-studied]"


def is_stub(entry):
    """True for a placeholder entry (dict or Entry), i.e. one still waiting for study."""
    what = entry.get("what") if isinstance(entry, dict) else getattr(entry, "what", "")
    return str(what or "").endswith(STUB_MARK)


class Tier(str, Enum):
    """Catalog tier. A str subclass that prints and serializes as its plain value.

    (str, Enum) plus __str__/__format__ instead of StrEnum, which needs Python 3.11:
    the engine supports 3.10+."""
    route = "route"      # core daily driver (rare); route_patterns are salience markers only
    catalog = "catalog"  # clearly useful
    lite = "lite"        # long-tail / stubs

    def __str__(self):
        return self.value

    def __format__(self, spec):
        return format(self.value, spec)

    @classmethod
    def coerce(cls, v):
        """Anything that isn't a valid tier -> catalog."""
        try:
            return cls(v)
        except ValueError:
            return cls.catalog


def offline_label(v):
    """The single tri-state vocabulary owner: True -> 'offline', 'partial' -> 'partial',
    anything else -> 'online'. Used by both the ARSENAL.md renderer and query output."""
    return "offline" if v is True else ("partial" if v == "partial" else "online")


def _text(v):
    """One entry field as text: None, lists and objects become "", other scalars str();
    characters UTF-8 can't hold (unpaired surrogates from a \\ud800 escape) become '?'."""
    if v is None or isinstance(v, (list, dict)):
        return ""
    s = v if isinstance(v, str) else str(v)
    return s.encode("utf-8", "replace").decode("utf-8")


@dataclass
class Entry:
    id: str = ""
    kind: str = ""
    name: str = ""
    what: str = ""
    use_when: str = ""
    avoid_when: str = ""
    offline: object = ""          # True | "partial" | "" | other (tri-state, see offline_label)
    cost: str = ""
    pairs_with: list = field(default_factory=list)
    supersedes: list = field(default_factory=list)
    triggers: list = field(default_factory=list)
    example: str = ""
    tier: Tier = Tier.catalog
    route_patterns: list = field(default_factory=list)

    @classmethod
    def from_raw(cls, d):
        """Normalize a raw study-fleet dict into an Entry (was assemble_catalog.normalize).

        List fields become a list-or-[]-or-[value] of strings; other fields become
        strings, defaulting to ""; offline keeps True / False / "partial"; a missing id falls
        back to slug(name) or 'unknown'; tier is coerced to the Tier vocabulary.
        Entry files come from study agents, so any JSON type can arrive here.
        """
        out = {}
        for k in FIELDS:
            v = d.get(k)
            if k in LIST_FIELDS:
                seq = v if isinstance(v, list) else ([] if v in (None, "") else [v])
                out[k] = [_text(x) for x in seq if x is not None and not isinstance(x, (list, dict))]
            elif k == "offline":
                out[k] = v if (v is True or v is False or v == "partial") else ""
            else:
                out[k] = _text(v)
        if not out["id"]:
            out["id"] = matching.slug(out["name"]) or "unknown"
        out["tier"] = Tier.coerce(out["tier"])
        return cls(**out)

    @classmethod
    def from_dict(cls, d):
        """Reconstruct an Entry from a serialized (to_dict) dict. Idempotent with from_raw."""
        return cls.from_raw(d)

    def to_dict(self):
        """Emit a plain dict with keys in FIELDS order (byte-identity of the JSON
        depends on insertion order). tier is emitted as a plain string."""
        d = {}
        for k in FIELDS:
            v = getattr(self, k)
            d[k] = str(v) if k == "tier" else v
        return d

    @classmethod
    def make_stub(cls, item):
        """Placeholder record for a newly-enumerated, not-yet-deep-studied tool (was
        weekly.make_stub). item is a raw enumeration dict with name/kind/desc, and
        `invoke` for skills (plugin skills: plugin:skill), which becomes the stub's name."""
        desc = (item.get("desc") or "").strip()
        name = item.get("invoke") or item.get("name") or "unknown"
        return cls(
            id=matching.slug(name), kind=item.get("kind", "skill"), name=name,
            what=(desc[:240] or f"{name} (no description found)") + " " + STUB_MARK,
            use_when=(f"Possibly relevant when the need matches: {desc[:160]}" if desc
                      else "Unknown until studied."),
            avoid_when="Stub entry pending deep study - details unverified; confirm against the tool itself before relying on it.",
            offline="", cost="", pairs_with=[], supersedes=[],
            triggers=[name], example="", tier=Tier.lite, route_patterns=[],
        )


def md_block(entry):
    """Render ONE entry as its ARSENAL.md block (heading + fields + a trailing blank
    line), returned as a string. Field order: What / Use when / Avoid when / Pairs with
    / Example."""
    off = offline_label(entry.offline)
    lines = [f"### {entry.name}  `{entry.kind}` - {off}, {entry.cost}"]
    if entry.what:
        lines.append(f"- **What:** {entry.what}")
    if entry.use_when:
        lines.append(f"- **Use when:** {entry.use_when}")
    if entry.avoid_when:
        lines.append(f"- **Avoid when:** {entry.avoid_when}")
    if entry.pairs_with:
        lines.append(f"- **Pairs with:** {', '.join(map(str, entry.pairs_with))}")
    if entry.example:
        lines.append(f"- **Example:** {entry.example}")
    lines.append("")
    return term_safe("\n".join(lines))


def render_md(entries, generated):
    """Render the full ARSENAL.md document string for a list of Entry records."""
    by_tier = collections.Counter(str(e.tier) for e in entries)
    L = ["# Your Arsenal - what you have and when to use it",
         f"_Auto-generated {generated} - {len(entries)} tools "
         f"({by_tier.get('route', 0)} core / {by_tier.get('catalog', 0)} catalog / "
         f"{by_tier.get('lite', 0)} long-tail)._",
         ""]
    for tier, head in (("route", "## Core (daily drivers)"),
                       ("catalog", "## Catalog (useful - ask your agent for them)"),
                       ("lite", "## Long-tail (installed, rarely needed)")):
        group = [e for e in entries if str(e.tier) == tier]
        if not group:
            continue
        L += [head, ""]
        for e in sorted(group, key=lambda x: (x.kind, x.id)):
            L.append(md_block(e))
    return "\n".join(L) + "\n"


def embed_text(entry):
    """The text embedded per skill for the semantic index: name(+id fallback), triggers,
    use_when, what - each str()-cast, joined with TWO spaces, stripped. avoid_when is
    deliberately excluded so 'when NOT to use X' doesn't pull X toward those prompts."""
    parts = [
        str(entry.name or entry.id or ""),
        " ".join(map(str, entry.triggers or [])),
        str(entry.use_when or ""),
        str(entry.what or ""),
    ]
    return "  ".join(p for p in parts if p).strip()
