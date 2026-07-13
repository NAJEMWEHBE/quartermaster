# -*- coding: utf-8 -*-
"""Owner of the catalog *match policy* - how a tool's name/id collapses to a key.

Every script that has to decide "is this the same tool?" imports these helpers;
none re-derive them. Defined ONCE, here. (Previously slug/nkey lived in config.py
and were re-implemented inline in several scripts.)
"""
import re


def slug(s):
    """Kebab-case slug: lowercase, non-alphanumerics -> '-', trimmed."""
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")


def nkey(s):
    """Match key: strip parenthetical suffixes so studied names and enumerated
    names collapse to the same key ('foo (plugin)' == 'foo')."""
    return slug(re.sub(r"\(.*?\)", "", str(s or "")))


def contains(k, keys):
    """Fuzzy containment for messy *model* tags ONLY (kind == "model").

    Model tags drift ('qwen3-embedding:0.6b' vs 'qwen3-embedding'), so we treat one
    as matching another when either contains the other. Both sides must be >= 8 chars
    so short ids don't collide by accident. Do NOT use this for skills/plugins/agents -
    their ids are authoritative and exact-match is correct there.
    """
    return any(len(k) >= 8 and len(o) >= 8 and (k in o or o in k) for o in keys)


def dedup_key(entry_id):
    """The catalog dedup key: case-folded id. First-loaded wins on a collision."""
    return entry_id.lower()
