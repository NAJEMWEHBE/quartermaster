# -*- coding: utf-8 -*-
"""The engine's runs, in-process, each returning a result object (counts and status are
data, not stdout to grep):

    enumerate_live(c, ws)                          -> EnumerateResult
    assemble(ws)                                   -> AssembleResult
    regen(c, ws, prune, force_prune, rebuild_index, embed) -> RegenResult
    weekly(c, ws, embed)                           -> WeeklyResult

`c` is a config dict (config.cfg()), `ws` its Workspace, `embed` an embedder (see
embedder.py; defaults to Ollama from the config). The CLIs in cli.py only parse
arguments and print these results.
"""
import collections
import datetime
import glob
import os
import re
import shutil
from dataclasses import dataclass, field

from . import catalog_file, index, inventory, workspace
from .embedder import OllamaEmbedder
from .entry import Entry, is_stub, render_md
from .matching import LiveSet, dedup_key, entry_keys, keys_of, nkey

# Exit codes shared by regen and weekly: 0 ok | 1 a step failed (nothing half-done) |
# 4 the catalog is up to date but the index build failed, so semantic search still uses
# the old index (the query side calls that INDEX-STALE).
EXIT_OK, EXIT_FAILED, EXIT_INDEX_FAILED = 0, 1, 4

# What reading one work-dir JSON file can raise: a missing or locked file, bad JSON or
# encoding (ValueError), or nesting deeper than the parser's recursion limit.
PARSE_ERRORS = (OSError, ValueError, RecursionError)

# Mass-prune circuit breaker: both must hold for a refusal, so small catalogs (and the
# test fixtures) always prune freely while a collapse-shaped prune needs force_prune
# (2026-07-19: a harness cache sweep read as 129 uninstalls and gutted the catalog).
PRUNE_GUARD_MIN = 10     # absolute floor: refusals need at least this many prunable items
PRUNE_GUARD_FRAC = 0.10  # relative: prunable share of the studied catalog above this

NON_ASCII = re.compile(r"[^\x00-\x7f]")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# --- enumerate ----------------------------------------------------------------------

@dataclass
class EnumerateResult:
    items: list
    counts: dict
    path: str


def enumerate_live(c, ws):
    """Scan the inventory and write arsenal_items.json. Raises inventory.InventoryError."""
    items = inventory.scan(c.get("scan", {}), c.get("embed", {}).get("url") or "http://127.0.0.1:11434")
    counts = dict(collections.Counter(i["kind"] for i in items))
    ws.write_json(workspace.ITEMS, {"items": items, "counts": counts, "total": len(items)})
    return EnumerateResult(items, counts, ws.path(workspace.ITEMS))


# --- assemble -----------------------------------------------------------------------

@dataclass
class AssembleResult:
    files: int
    loaded: int
    unique: int
    dups: int
    by_tier: dict
    by_kind: dict
    warnings: int

    def summary(self):
        return (f"batch files: {self.files} | entries loaded: {self.loaded} | "
                f"unique: {self.unique} | dups: {self.dups}")


def load_batches(ws):
    """[(file name, raw entry dict)] from entries/batch-*.json in name order (so deep
    batches load before the zz stub file), plus warnings and the file count."""
    entries, warns = [], []
    files = sorted(glob.glob(ws.path(workspace.ENTRIES, "batch-*.json")))
    for fp in files:
        try:
            data = workspace.read_json(fp)
        except PARSE_ERRORS as e:
            warns.append(f"UNPARSEABLE {os.path.basename(fp)}: {type(e).__name__}: {e}")
            continue
        if isinstance(data, dict) and "items" in data:
            data = data["items"]
        if not isinstance(data, list):
            warns.append(f"NOT-A-LIST {os.path.basename(fp)}")
            continue
        entries.extend((os.path.basename(fp), e) for e in data if isinstance(e, dict))
    return entries, warns, len(files)


def assemble(ws):
    """Merge the batch files into arsenal.json, ARSENAL.md and quality-report.txt.
    Dedup is by (kind, id), first-loaded wins; malformed entries are skipped and reported."""
    raw, warns, nfiles = load_batches(ws)
    seen, items, dups = set(), [], []
    for src, e in raw:
        ent = Entry.from_raw(e)
        key = dedup_key(ent.kind, ent.id)
        if key in seen:
            dups.append(f"{ent.id} (dup in {src}, kept first; kind {ent.kind or '?'})")
            continue
        seen.add(key)
        items.append(ent)

    qual = list(warns)
    for ent in items:
        miss = [f for f in ("what", "use_when", "avoid_when", "tier") if not getattr(ent, f)]
        if miss:
            qual.append(f"{ent.id}: missing {miss}")
        for p in ent.route_patterns:
            if NON_ASCII.search(p):
                qual.append(f"{ent.id}: NON-ASCII route pattern: {p!r}")
        if ent.tier == "route" and not ent.route_patterns:
            qual.append(f"{ent.id}: tier=route but NO route_patterns")
    if dups:
        qual.append("--- DUPS ---")
        qual.extend(dups)

    generated = _now()
    payload = catalog_file.write(ws.path(workspace.CATALOG), items, generated=generated)
    ws.write_text(workspace.CATALOG_MD, render_md(items, generated))
    ws.write_text(workspace.QUALITY, "\n".join(qual) + "\n" if qual else "clean - no warnings\n")
    return AssembleResult(nfiles, len(raw), len(items), len(dups),
                          payload["by_tier"], payload["by_kind"], len(qual))


# --- regen --------------------------------------------------------------------------

def diff(live, studied):
    """(added, removed, unchanged) between the live inventory and the studied catalog,
    by tool identity (see matching.LiveSet): kind-aware, plugin skills as plugin:skill."""
    now = LiveSet(live)
    known = keys_of(studied)
    added = [it for it in now.items if not now.known(it, known)]
    removed = [it for it in studied if not now.covers(it)]
    return added, removed, len(studied) - len(removed)


def study_queue(live, studied):
    """Every live tool with no deep entry yet (new ones and stubbed ones alike), each with
    the id its entry should get and what a study agent reads: desc and source path."""
    now = LiveSet(live)
    deep = keys_of(e for e in studied if not is_stub(e))
    return [{"id": Entry.make_stub(it).id, **it} for it in now.items if not now.known(it, deep)]


def write_study_queue(ws, queue, generated):
    """Rewrite study_queue.json from scratch every run; no file when nothing is pending."""
    ws.remove(workspace.LEGACY_TODO)
    if queue:
        ws.write_json(workspace.STUDY_QUEUE, {"generated": generated, "count": len(queue), "items": queue})
    else:
        ws.remove(workspace.STUDY_QUEUE)


@dataclass
class RegenResult:
    status: int = EXIT_OK
    error: str = ""
    live: list = field(default_factory=list)
    studied_total: int = 0
    unchanged: int = 0
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    shared: list = field(default_factory=list)  # removed only because their name is now shared
    queue: list = field(default_factory=list)
    pruned: int = 0
    kept: int = 0
    prune_refused: str = ""
    index: str = ""        # "" not asked | "ok" | "FAILED"
    index_error: str = ""

    def lines(self):
        if self.error:
            return [f"ERROR: {self.error}"]
        out = [f"LIVE inventory: {len(self.live)}  |  STUDIED catalog: {self.studied_total}",
               f"  unchanged: {self.unchanged}",
               f"  NEW (need study): {len(self.added)}",
               f"  REMOVED (uninstalled): {len(self.removed)}"]
        if self.shared:
            out.append(f"    of which {len(self.shared)} have a name now shared by several live "
                       f"skills; study each as plugin:skill: {', '.join(map(str, self.shared[:10]))}"
                       + (" ..." if len(self.shared) > 10 else ""))
        if self.queue:
            out.append(f"  -> wrote {workspace.STUDY_QUEUE} ({len(self.queue)} items)")
        if self.prune_refused:
            out.append(f"  PRUNE REFUSED: {self.prune_refused}")
        elif self.pruned:
            out.append(f"  PRUNED {self.pruned} items -> {workspace.CATALOG} ({self.kept} left, .bak written)")
        if self.index:
            out.append(f"  build_index: {self.index}")
        if self.index_error:
            out.append(f"    {self.index_error}")
        if not self.added and not self.removed:
            out.append("CATALOG FRESH - no changes since last study.")
        return out


def _prune_key(entry):
    return (entry.get("kind") or "", nkey(entry.get("id") or entry.get("name")))


def _pruned_last(ws):
    try:
        return {tuple(k) for k in ws.read_json(workspace.PRUNED_LAST)}
    except (OSError, ValueError, TypeError):
        return set()


def regen(c, ws, prune=False, force_prune=False, rebuild_index=False, embed=None):
    """Re-enumerate, diff against the catalog, rewrite the plan and the study queue, and
    optionally prune uninstalled tools and rebuild the index. Models are never pruned
    (their tags match fuzzily). A prune that would newly drop >= PRUNE_GUARD_MIN items AND
    > PRUNE_GUARD_FRAC of the catalog is refused unless force_prune: that shape almost
    always means the scan collapsed (unmounted root, swept cache), not a mass uninstall.
    "Newly" = not removed by the last prune (pruned_last.json): assemble brings pruned
    entries back every week, and one accepted force_prune must not be refused again."""
    try:
        live = enumerate_live(c, ws).items
    except (inventory.InventoryError, OSError, ValueError) as e:
        # ValueError includes UnicodeError: a name UTF-8 can't hold, so the message is
        # escaped where it can't be written as is
        why = str(e).encode("utf-8", "backslashreplace").decode("utf-8")
        return RegenResult(status=EXIT_FAILED, error=f"enumerate failed: {why}")
    try:
        cat = ws.read_json(workspace.CATALOG)
    except PARSE_ERRORS:
        cat = {}
    studied = cat.get("items") if isinstance(cat, dict) else None
    studied = [e for e in studied if isinstance(e, dict)] if isinstance(studied, list) else []

    added, removed, unchanged = diff(live, studied)
    now = LiveSet(live)
    r = RegenResult(live=live, studied_total=len(studied), unchanged=unchanged,
                    added=added, removed=removed,
                    shared=[i.get("id") or i.get("name") for i in removed if now.shared(i)])
    generated = _now()
    ws.write_json(workspace.PLAN, {
        "generated": generated, "live_total": len(live), "studied_total": len(studied),
        "unchanged": unchanged, "added": added,
        "removed": [{"id": i.get("id"), "name": i.get("name"), "kind": i.get("kind")} for i in removed]})
    r.queue = study_queue(live, studied)
    write_study_queue(ws, r.queue, generated)

    prunable = [i for i in removed if i.get("kind") != "model"]
    # assemble restores every batch entry each week, so a removal the last prune already
    # made shows up again; only removals that are new since then count toward the guard.
    last = _pruned_last(ws)
    fresh = [i for i in prunable if _prune_key(i) not in last]
    frac = len(fresh) / len(studied) if studied else 0.0
    if prune and not force_prune and len(fresh) >= PRUNE_GUARD_MIN and frac > PRUNE_GUARD_FRAC:
        r.prune_refused = (f"{len(fresh)}/{len(studied)} studied items ({frac:.0%}) would newly be "
                           f"dropped — that shape usually means the LIVE enumeration collapsed, "
                           f"not a mass uninstall. Check scan.skill_roots, then rerun with "
                           f"--force-prune if the removals are real.")
    elif prune and prunable and studied:
        path = ws.path(workspace.CATALOG)
        # Prune through catalog_file so the header is recomputed, and re-render ARSENAL.md.
        _, entries = catalog_file.parse(path)
        kept = [e for e in entries if e.kind == "model" or now.covers(e)]
        shutil.copy2(path, path + ".bak")
        payload = catalog_file.write(path, kept)
        ws.write_text(workspace.CATALOG_MD, render_md(kept, payload["generated"]))
        ws.write_json(workspace.PRUNED_LAST, sorted({_prune_key(i) for i in prunable}))
        r.pruned, r.kept = len(prunable), len(kept)

    if rebuild_index:
        embed = embed or OllamaEmbedder.from_config(c)
        try:
            _, entries = catalog_file.parse(ws.path(workspace.CATALOG))
            index.build(ws, entries, embed)
            r.index = "ok"
        except (ImportError, OSError, ValueError, RuntimeError) as e:  # ImportError: no numpy
            r.index, r.index_error = "FAILED", f"{type(e).__name__}: {e}"
            r.status = EXIT_INDEX_FAILED
    return r


# --- weekly -------------------------------------------------------------------------

def stub_queue(added, old_stubs, deep_keys, live):
    """The stubs to keep = (old stubs + newly-added) minus deep-covered minus uninstalled.

    A stub retires the moment a deep entry identifies the same live tool, or the tool
    stops being installed. Identity is matching.LiveSet's (kind-aware, plugin:skill).
    Returns Entry records sorted by key.
    added    : raw enumeration dicts for NEW tools
    old_stubs: existing stub Entry records
    deep_keys: (kind, key) pairs of every deep (non-stub) entry, see matching.keys_of
    live     : the live inventory items (or a matching.LiveSet)
    """
    now = live if isinstance(live, LiveSet) else LiveSet(live)
    merged = {}
    for e in old_stubs:
        merged[(e.kind, nkey(e.id))] = e
    for it in added:
        s = Entry.make_stub(it)
        merged.setdefault((s.kind, nkey(s.id)), s)
    kept = []
    for k, e in sorted(merged.items()):
        tools = now.matched_by(entry_keys(e))
        if k[1] and tools and not any(now.known(t, deep_keys) for t in tools):
            kept.append(e)
    return kept


def _deep_entries(ws):
    stubs = os.path.abspath(ws.path(workspace.STUBS))
    deep = []
    for fp in glob.glob(ws.path(workspace.ENTRIES, "batch-*.json")):
        if os.path.abspath(fp) == stubs:
            continue
        try:
            data = workspace.read_json(fp)
        except PARSE_ERRORS:
            continue
        items = data.get("items", data) if isinstance(data, dict) else data
        deep += [Entry.from_raw(e) for e in (items if isinstance(items, list) else [])
                 if isinstance(e, dict)]
    return deep


def _old_stubs(ws):
    try:
        old = ws.read_json(workspace.STUBS)
    except PARSE_ERRORS:
        return []
    rows = old.get("items", old) if isinstance(old, dict) else old
    return [Entry.from_dict(e) for e in rows if isinstance(e, dict)] if isinstance(rows, list) else []


# The regen lines the weekly log keeps (the rest is in regen_plan.json).
WEEKLY_LOGGED = ("LIVE inventory", "PRUNED", "PRUNE REFUSED", "build_index", "CATALOG FRESH")


@dataclass
class WeeklyResult:
    status: int
    pending: int = 0
    catalog: int = 0


def weekly(c, ws, embed=None):
    """The zero-LLM self-maintenance run: diff, refresh stubs (new tools get placeholder
    entries so queries see them; stubs retire when a deep entry appears or the tool is
    uninstalled), assemble, prune + rebuild the index, optional copy. Logs every step
    through ws.log."""
    os.makedirs(ws.path(workspace.ENTRIES), exist_ok=True)
    ws.log("=== quartermaster weekly start ===")

    r = regen(c, ws)
    ws.log("diff: " + r.lines()[0])
    if r.status != EXIT_OK:
        return WeeklyResult(EXIT_FAILED)

    kept = stub_queue(r.added, _old_stubs(ws), keys_of(_deep_entries(ws)), r.live)
    ws.write_json(workspace.STUBS, [e.to_dict() for e in kept], indent=1)
    ws.log(f"stubs: {len(r.added)} new diffed, {len(kept)} pending study (the queue)")

    try:
        a = assemble(ws)
    except Exception as e:  # the scheduled run logs why it stopped instead of a bare traceback
        ws.log(f"FATAL: assemble failed: {type(e).__name__}: {e}")
        return WeeklyResult(EXIT_FAILED)
    ws.log("assemble: " + a.summary())

    r = regen(c, ws, prune=True, rebuild_index=True, embed=embed)
    if r.error:
        ws.log(f"FATAL: prune/index failed: {r.error}")
        return WeeklyResult(EXIT_FAILED)
    for line in r.lines():
        if any(k in line for k in WEEKLY_LOGGED):
            ws.log("regen: " + line.strip())
    if r.status == EXIT_INDEX_FAILED:
        ws.log(f"INDEX STALE: build_index failed ({r.index_error}); queries use the last complete "
               f"index, or report INDEX-STALE, until a rebuild works")

    dest = c.get("copy_to")
    if dest:
        with open(ws.path(workspace.CATALOG), "rb") as src:
            data = src.read()
        workspace.write_with(dest, lambda f: f.write(data), mode="wb")
        ws.log(f"copied {workspace.CATALOG} -> {dest}")

    count = ws.read_json(workspace.CATALOG)["count"]
    ws.log(f"=== done. catalog {count} | pending study {len(kept)} ===")
    return WeeklyResult(r.status, len(kept), count)
