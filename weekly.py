# -*- coding: utf-8 -*-
"""The recurring self-maintenance run (schedule it weekly; see README).

Zero-LLM-cost chain:
  1. regen_arsenal.py                 - re-enumerate + diff
  2. stub maintenance                 - NEW items get placeholder entries in
                                        entries/batch-zz-stubs.json so queries see them;
                                        stubs auto-retire when a deep entry appears or the
                                        tool is uninstalled. The stub file IS the study queue.
  3. assemble_catalog.py              - rebuild catalog (deep entries shadow stubs:
                                        'zz' sorts last, dedup keeps first-loaded)
  4. regen_arsenal.py --prune --rebuild-index
  5. optional extra copy of arsenal.json (config "copy_to")

Deep study stays manual and human-approved: when the log says 'pending study: N',
point your agent at the stub queue with prompts/study-agent.md. No tokens spent here.
"""
import glob
import json
import os
import shutil
import subprocess
import sys

from config import cfg, log, work_path
from entry import Entry
from matching import nkey

PY = sys.executable
HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    r = subprocess.run([PY, os.path.join(HERE, script), *args],
                       capture_output=True, text=True, timeout=1800)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def stub_queue(added, old_stubs, deep_keys, live_keys):
    """The study queue = (old stubs + newly-added) minus deep-covered minus uninstalled.

    A stub retires the moment a deep entry for its key appears (deep_keys) or the tool
    stops being installed (not in live_keys). Returns Entry records sorted by key.
    added   : raw enumeration dicts for NEW tools
    old_stubs: existing stub Entry records
    """
    merged = {}
    for e in old_stubs:
        merged[nkey(e.id)] = e
    for it in added:
        s = Entry.make_stub(it)
        merged.setdefault(nkey(s.id), s)
    return [e for k, e in sorted(merged.items())
            if k and k not in deep_keys and k in live_keys]


def main():
    stubs_path = os.path.join(work_path("entries"), "batch-zz-stubs.json")
    os.makedirs(work_path("entries"), exist_ok=True)
    log("=== quartermaster weekly start ===")

    rc, out = run("regen_arsenal.py")
    log("diff: " + (out.strip().splitlines()[0] if out.strip() else f"rc={rc}"))
    if rc != 0:
        log(f"FATAL: diff failed: {out[-300:]}")
        return 1
    plan = json.load(open(work_path("regen_plan.json"), encoding="utf-8"))
    added = plan.get("added", [])

    # stub maintenance: (old stubs + newly added) - deep-covered - uninstalled
    deep = set()
    for fp in glob.glob(os.path.join(work_path("entries"), "batch-*.json")):
        if os.path.abspath(fp) == os.path.abspath(stubs_path):
            continue
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items = data.get("items", data) if isinstance(data, dict) else data
        for e in items if isinstance(items, list) else []:
            if isinstance(e, dict):
                deep.add(nkey(e.get("id")))
                deep.add(nkey(e.get("name")))
    live_keys = {nkey(i.get("name")) for i in
                 json.load(open(work_path("arsenal_items.json"), encoding="utf-8")).get("items", [])}
    old_stubs = []
    if os.path.exists(stubs_path):
        try:
            old = json.load(open(stubs_path, encoding="utf-8"))
            old_stubs = [Entry.from_dict(e) for e in
                         (old.get("items", old) if isinstance(old, dict) else old)
                         if isinstance(e, dict)]
        except (OSError, json.JSONDecodeError):
            pass
    kept = stub_queue(added, old_stubs, deep, live_keys)
    json.dump([e.to_dict() for e in kept], open(stubs_path, "w", encoding="utf-8"),
              indent=1, ensure_ascii=False)
    log(f"stubs: {len(added)} new diffed, {len(kept)} pending study (the queue)")

    rc, out = run("assemble_catalog.py")
    log("assemble: " + next((l for l in out.splitlines() if l.startswith("batch files")), f"rc={rc}"))
    if rc != 0:
        log(f"FATAL: assemble failed: {out[-300:]}")
        return 1
    rc, out = run("regen_arsenal.py", "--prune", "--rebuild-index")
    for l in out.strip().splitlines():
        if any(k in l for k in ("LIVE inventory", "PRUNED", "PRUNE REFUSED", "build_index", "CATALOG FRESH")):
            log("regen: " + l.strip())
    if rc != 0:
        log(f"FATAL: prune/index failed: {out[-300:]}")
        return 1

    dest = cfg().get("copy_to")
    if dest:
        shutil.copy2(work_path("arsenal.json"), os.path.expanduser(dest))
        log(f"copied arsenal.json -> {dest}")

    cat = json.load(open(work_path("arsenal.json"), encoding="utf-8"))
    log(f"=== done. catalog {cat['count']} | pending study {len(kept)} ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
