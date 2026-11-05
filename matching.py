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


def dedup_key(kind, entry_id):
    """The catalog dedup key: (kind, case-folded id). A plugin `foo` and its skill `foo`
    are two entries. First-loaded wins on a collision."""
    return (kind or "", entry_id.lower())


# --- Tool identity: "is this catalog entry the same tool as that live item?" ---------
#
# A live item is known by (kind, nkey(invoke or name)): plugin skills are `plugin:skill`,
# so two plugins' `access` skills are two tools, and a plugin `foo` is not its skill `foo`.
# Catalog entries answer to (kind, nkey(id)) and (kind, nkey(name)). Entries studied
# before plugin:skill identity carry the bare skill name; that alias still identifies a
# live item, but only while no other live item of the same kind shares the bare name.

def _get(obj, k):
    return obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)


def live_key(item):
    """(kind, key) identity of a live inventory item."""
    return (_get(item, "kind") or "", nkey(_get(item, "invoke") or _get(item, "name")))


def _alias(item):
    return (_get(item, "kind") or "", nkey(_get(item, "name")))


def entry_keys(entry):
    """The (kind, key) pairs a catalog entry (dict or Entry) answers to."""
    kind = _get(entry, "kind") or ""
    return {(kind, k) for k in (nkey(_get(entry, "id")), nkey(_get(entry, "name"))) if k}


def _expand(keys, kinds):
    """An entry with no kind (hand-written or legacy) answers to its key in every kind."""
    out = set()
    for kind, k in keys:
        out |= {(kd, k) for kd in kinds} if not kind else {(kind, k)}
    return out


def keys_of(entries):
    out = set()
    for e in entries:
        out |= entry_keys(e)
    return out


class LiveSet:
    """The live inventory, indexed for identity questions."""

    def __init__(self, items):
        self.by_key = {}
        aliases = {}
        for it in items:
            k = live_key(it)
            if k[1]:
                self.by_key.setdefault(k, it)  # first one wins on an exact duplicate
        for it in self.by_key.values():
            a = _alias(it)
            if a[1]:
                aliases.setdefault(a, []).append(it)
        self._alias = {a: its[0] for a, its in aliases.items() if len(its) == 1}
        self._shared = {a for a, its in aliases.items() if len(its) > 1}
        self._models = [k[1] for k in self.by_key if k[0] == "model"]
        self._kinds = {k[0] for k in self.by_key}

    @property
    def items(self):
        return list(self.by_key.values())

    def matched_by(self, keys):
        """Live items that a set of (kind, key) pairs identifies."""
        keys = _expand(keys, self._kinds)
        hit = [self.by_key[k] for k in keys if k in self.by_key]
        hit += [self._alias[k] for k in keys if k in self._alias and self._alias[k] not in hit]
        return hit

    def covers(self, entry):
        """True if the catalog entry still stands for something installed. Models match
        fuzzily (their tags drift); see contains()."""
        keys = _expand(entry_keys(entry), self._kinds | {"model"})
        if self.matched_by(keys):
            return True
        return any(kind == "model" and contains(k, self._models) for kind, k in keys)

    def shared(self, entry):
        """True if the entry's bare name now belongs to several live skills (say two
        plugins' `access`), so it identifies none of them and needs re-study."""
        return bool(_expand(entry_keys(entry), self._kinds) & self._shared)

    def known(self, item, keys):
        """True if `keys` (from catalog entries) already identify this live item."""
        k, a = live_key(item), _alias(item)
        keys = _expand(keys, {k[0]})
        if k in keys or (a in keys and self._alias.get(a) is item):
            return True
        return k[0] == "model" and contains(k[1], [x for kind, x in keys if kind == "model"])
