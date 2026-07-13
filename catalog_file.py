# -*- coding: utf-8 -*-
"""Owner of the arsenal.json *serialized contract* - the top-level catalog file.

The file is always {generated, count, by_tier, by_kind, items}. This module is the
only place that assembles that payload, so every writer produces a consistent header:
count/by_tier/by_kind are ALWAYS recomputed from the items being written. (The old
regen --prune patched items+count in place and left by_tier/by_kind/generated stale -
that bug is impossible now: every write goes through build().)
"""
import collections
import datetime
import json

from entry import Entry


def build(items, generated=None):
    """Assemble the arsenal.json payload dict from a list of Entry records.

    `generated` is injectable for deterministic tests; it defaults to now(). The header
    (count/by_tier/by_kind) is recomputed from `items` every time - readers can trust it.
    """
    if generated is None:
        generated = datetime.datetime.now().isoformat(timespec="seconds")
    ordered = sorted(items, key=lambda e: (e.tier != "route", e.kind, e.id))
    return {
        "generated": generated,
        "count": len(items),
        "by_tier": dict(collections.Counter(str(e.tier) for e in items)),
        "by_kind": dict(collections.Counter(e.kind for e in items)),
        "items": [e.to_dict() for e in ordered],
    }


def write(path, items, generated=None):
    """Write arsenal.json (indent=2, ensure_ascii=False). Returns the payload dict."""
    payload = build(items, generated)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return payload


def parse(path):
    """Read arsenal.json -> (header dict without 'items', list[Entry])."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    header = {k: v for k, v in data.items() if k != "items"}
    entries = [Entry.from_dict(d) for d in data.get("items", [])]
    return header, entries
