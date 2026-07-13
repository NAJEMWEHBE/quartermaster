# -*- coding: utf-8 -*-
"""Merge study-fleet batch files into the catalog.

Reads <work_dir>/entries/batch-*.json (each a JSON array of entries, or {"items":[...]}),
normalizes + dedups (first-loaded wins, so deep entries shadow the zz-stubs file), writes:
  arsenal.json        - machine catalog
  ARSENAL.md          - human-readable copy grouped by tier
  quality-report.txt  - missing fields / duplicates / warnings
Tolerant of malformed entries: skips and reports rather than crashing.

The entry record, its normalization, the arsenal.json contract and the ARSENAL.md
renderer are all owned elsewhere (entry.py / catalog_file.py); this script only
orchestrates loading, dedup, quality reporting and file placement.
"""
import datetime
import glob
import json
import os
import re

import catalog_file
from config import cfg, entries_dir, work_path
from entry import Entry, render_md
from matching import dedup_key

NON_ASCII = re.compile(r"[^\x00-\x7f]")


def load_entries():
    entries, warns = [], []
    files = sorted(glob.glob(os.path.join(entries_dir(), "batch-*.json")))
    for fp in files:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            warns.append(f"UNPARSEABLE {os.path.basename(fp)}: {e}")
            continue
        if isinstance(data, dict) and "items" in data:
            data = data["items"]
        if not isinstance(data, list):
            warns.append(f"NOT-A-LIST {os.path.basename(fp)}")
            continue
        entries.extend((os.path.basename(fp), e) for e in data if isinstance(e, dict))
    return entries, warns, len(files)


def main():
    raw, warns, nfiles = load_entries()
    seen, items, dups = set(), [], []
    for src, e in raw:
        ent = Entry.from_raw(e)
        key = dedup_key(ent.id)
        if key in seen:
            dups.append(f"{key} (dup in {src}, kept first)")
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

    generated = datetime.datetime.now().isoformat(timespec="seconds")
    payload = catalog_file.write(work_path("arsenal.json"), items, generated=generated)
    with open(work_path("ARSENAL.md"), "w", encoding="utf-8") as f:
        f.write(render_md(items, generated))
    with open(work_path("quality-report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(qual) + "\n" if qual else "clean - no warnings\n")

    print(f"batch files: {nfiles} | entries loaded: {len(raw)} | unique: {len(items)} | dups: {len(dups)}")
    print(f"by_tier: {payload['by_tier']} | by_kind: {payload['by_kind']}")
    print(f"quality warnings: {len(qual)}")
    print("wrote: arsenal.json, ARSENAL.md, quality-report.txt")


if __name__ == "__main__":
    main()
