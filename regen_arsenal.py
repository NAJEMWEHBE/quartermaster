# -*- coding: utf-8 -*-
"""Diff the LIVE arsenal against the studied catalog; optionally prune + rebuild index.

Modes:
  python regen_arsenal.py                    # diff only. writes regen_plan.json, and
                                             # study_queue.json while anything is unstudied
  python regen_arsenal.py --prune            # also drop REMOVED items from arsenal.json (+.bak)
  python regen_arsenal.py --rebuild-index    # also run build_index.py (exit 4 if it fails)
  python regen_arsenal.py --prune --force-prune   # override the mass-prune guard
Models are never auto-pruned (their tag matching is fuzzy).
A prune that would drop >= PRUNE_GUARD_MIN items AND > PRUNE_GUARD_FRAC of the studied
catalog is refused without --force-prune: that shape almost always means the LIVE
enumeration collapsed (unmounted root, swept plugin cache), not a real mass uninstall
(2026-07-19: a harness cache sweep read as 129 uninstalls and gutted the catalog).
While study_queue.json exists: have your agent study it (see prompts/study-agent.md),
then run assemble_catalog.py, then this with --prune --rebuild-index.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

import catalog_file
from config import cfg, work_path
from entry import Entry, is_stub, render_md
from matching import LiveSet, keys_of

PY = sys.executable

# Exit codes: 0 ok | 1 enumerate failed (nothing changed) | 4 the catalog step finished but
# the index build failed, so semantic search still uses the old index (query's INDEX-STALE).
EXIT_INDEX_FAILED = 4

# Mass-prune circuit breaker: both must hold for a refusal, so small catalogs (and the
# test fixtures) always prune freely while a collapse-shaped prune needs --force-prune.
PRUNE_GUARD_MIN = 10     # absolute floor: refusals need at least this many prunable items
PRUNE_GUARD_FRAC = 0.10  # relative: prunable share of the studied catalog above this


def run_here(script, *args):
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([PY, os.path.join(here, script), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def diff(live, studied):
    """(added, removed, unchanged) between the live inventory and the studied catalog,
    by tool identity (see matching.LiveSet): kind-aware, plugin skills as plugin:skill."""
    now = LiveSet(live)
    known = keys_of(studied)
    added = [it for it in now.items if not now.known(it, known)]
    removed = [it for it in studied if not now.covers(it)]
    return added, removed, len(studied) - len(removed)


STUDY_QUEUE = "study_queue.json"
LEGACY_TODO = "regen_study_todo.json"  # the old, NEW-only queue that went stale


def study_queue(live, studied):
    """Every live tool with no deep entry yet (new ones and stubbed ones alike), each with
    the id its entry should get and what a study agent reads: desc and source path."""
    now = LiveSet(live)
    deep = keys_of(e for e in studied if not is_stub(e))
    queue = []
    for it in now.items:
        if not now.known(it, deep):
            queue.append({"id": Entry.make_stub(it).id, **it})
    return queue


def write_study_queue(queue, generated):
    """Rewrite study_queue.json from scratch every run; no file when nothing is pending."""
    for name in (STUDY_QUEUE, LEGACY_TODO):
        try:
            os.remove(work_path(name))
        except FileNotFoundError:
            pass
    if queue:
        with open(work_path(STUDY_QUEUE), "w", encoding="utf-8") as f:
            json.dump({"generated": generated, "count": len(queue), "items": queue}, f,
                      indent=2, ensure_ascii=False)


def main():
    flags = set(sys.argv[1:])
    rc, out = run_here("enumerate_arsenal.py")
    if rc != 0:
        print("ERROR: enumerate failed:", out[-300:])
        return 1
    live = json.load(open(work_path("arsenal_items.json"), encoding="utf-8")).get("items", [])
    try:
        studied = json.load(open(work_path("arsenal.json"), encoding="utf-8")).get("items", [])
    except (OSError, json.JSONDecodeError):
        studied = []

    added, removed, unchanged = diff(live, studied)
    print(f"LIVE inventory: {len(live)}  |  STUDIED catalog: {len(studied)}")
    print(f"  unchanged: {unchanged}")
    print(f"  NEW (need study): {len(added)}")
    print(f"  REMOVED (uninstalled): {len(removed)}")

    plan = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "live_total": len(live), "studied_total": len(studied), "unchanged": unchanged,
            "added": added,
            "removed": [{"id": i.get("id"), "name": i.get("name"), "kind": i.get("kind")} for i in removed]}
    with open(work_path("regen_plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    queue = study_queue(live, studied)
    write_study_queue(queue, plan["generated"])
    if queue:
        print(f"  -> wrote {STUDY_QUEUE} ({len(queue)} items)")

    prunable = [i for i in removed if i.get("kind") != "model"]
    frac = len(prunable) / len(studied) if studied else 0.0
    if ("--prune" in flags and "--force-prune" not in flags
            and len(prunable) >= PRUNE_GUARD_MIN and frac > PRUNE_GUARD_FRAC):
        print(f"  PRUNE REFUSED: {len(prunable)}/{len(studied)} studied items ({frac:.0%}) "
              f"would be dropped — that shape usually means the LIVE enumeration collapsed, "
              f"not a mass uninstall. Check scan.skill_roots, then rerun with --force-prune "
              f"if the removals are real.")
    elif "--prune" in flags and prunable and studied:
        now = LiveSet(live)
        path = work_path("arsenal.json")
        # Structural fix: prune through the catalog_file owner so the header
        # (count/by_tier/by_kind/generated) is recomputed instead of patched in place -
        # the old in-place patch left by_tier/by_kind/generated stale. The kept ITEMS
        # are the same as before; only the header is now consistent. ARSENAL.md is also
        # regenerated (the old prune left it stale).
        _, entries = catalog_file.parse(path)
        kept = [e for e in entries if e.kind == "model" or now.covers(e)]
        shutil.copy2(path, path + ".bak")
        payload = catalog_file.write(path, kept)
        with open(work_path("ARSENAL.md"), "w", encoding="utf-8") as f:
            f.write(render_md(kept, payload["generated"]))
        print(f"  PRUNED {len(prunable)} items -> arsenal.json ({len(kept)} left, .bak written)")

    status = 0
    if "--rebuild-index" in flags:
        rc, out = run_here("build_index.py")
        print(f"  build_index.py: {'ok' if rc == 0 else 'FAILED'}")
        if rc != 0:
            print(out[-300:])
            status = EXIT_INDEX_FAILED

    if not added and not removed:
        print("CATALOG FRESH - no changes since last study.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
