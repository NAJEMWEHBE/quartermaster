# -*- coding: utf-8 -*-
"""Diff the LIVE arsenal against the studied catalog; optionally prune + rebuild index.

Modes:
  python regen_arsenal.py                    # diff only (read-only). writes regen_plan.json
                                             # + regen_study_todo.json when new items exist
  python regen_arsenal.py --prune            # also drop REMOVED items from arsenal.json (+.bak)
  python regen_arsenal.py --rebuild-index    # also run build_index.py
Models are never auto-pruned (their tag matching is fuzzy).
After NEW items appear: have your agent study regen_study_todo.json (see prompts/study-agent.md),
then run assemble_catalog.py, then this with --prune --rebuild-index.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys

from config import cfg, nkey, work_path

PY = sys.executable


def run_here(script, *args):
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([PY, os.path.join(here, script), *args], capture_output=True, text=True)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def diff(live, studied):
    studied_slugs = {}
    for it in studied:
        for k in {nkey(it.get("name")), nkey(it.get("id"))}:
            if k:
                studied_slugs.setdefault(k, it)
    live_slugs = {nkey(it.get("name")): it for it in live if nkey(it.get("name"))}

    def contains(k, keys):  # fuzzy containment for messy model tags only
        return any(len(k) >= 8 and len(o) >= 8 and (k in o or o in k) for o in keys)

    added = [it for s, it in live_slugs.items()
             if s not in studied_slugs
             and not (it.get("kind") == "model" and contains(s, list(studied_slugs)))]
    removed = []
    for it in studied:
        kn, ki = nkey(it.get("name")), nkey(it.get("id"))
        if kn in live_slugs or ki in live_slugs:
            continue
        if it.get("kind") == "model" and (contains(kn, list(live_slugs)) or contains(ki, list(live_slugs))):
            continue
        removed.append(it)
    return added, removed, len(studied) - len(removed)


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
    json.dump(plan, open(work_path("regen_plan.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    if added:
        json.dump({"items": added}, open(work_path("regen_study_todo.json"), "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)
        print(f"  -> wrote regen_study_todo.json ({len(added)} items)")

    prunable = [i for i in removed if i.get("kind") != "model"]
    if "--prune" in flags and prunable and studied:
        rm = {nkey(i.get("name")) for i in prunable} | {nkey(i.get("id")) for i in prunable}
        kept = [it for it in studied if nkey(it.get("name")) not in rm and nkey(it.get("id")) not in rm]
        path = work_path("arsenal.json")
        shutil.copy2(path, path + ".bak")
        full = json.load(open(path, encoding="utf-8"))
        full["items"], full["count"] = kept, len(kept)
        json.dump(full, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        print(f"  PRUNED {len(prunable)} items -> arsenal.json ({len(kept)} left, .bak written)")

    if "--rebuild-index" in flags:
        rc, out = run_here("build_index.py")
        print(f"  build_index.py: {'ok' if rc == 0 else 'FAILED'}")
        if rc != 0:
            print(out[-300:])

    if not added and not removed:
        print("CATALOG FRESH - no changes since last study.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
