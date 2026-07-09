# -*- coding: utf-8 -*-
"""Merge study-fleet batch files into the catalog.

Reads <work_dir>/entries/batch-*.json (each a JSON array of entries, or {"items":[...]}),
normalizes + dedups (first-loaded wins, so deep entries shadow the zz-stubs file), writes:
  arsenal.json        - machine catalog
  ARSENAL.md          - human-readable copy grouped by tier
  quality-report.txt  - missing fields / duplicates / warnings
Tolerant of malformed entries: skips and reports rather than crashing.
"""
import collections
import datetime
import glob
import json
import os

from config import cfg, entries_dir, slug, work_path

FIELDS = ["id", "kind", "name", "what", "use_when", "avoid_when", "offline",
          "cost", "pairs_with", "supersedes", "triggers", "example", "tier", "route_patterns"]
LIST_FIELDS = {"pairs_with", "supersedes", "triggers", "route_patterns"}


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


def normalize(e):
    out = {}
    for k in FIELDS:
        v = e.get(k)
        if k in LIST_FIELDS:
            out[k] = v if isinstance(v, list) else ([] if v in (None, "") else [v])
        else:
            out[k] = v if v is not None else ""
    if not out["id"]:
        out["id"] = slug(out["name"]) or "unknown"
    if out["tier"] not in ("route", "catalog", "lite"):
        out["tier"] = "catalog"
    return out


def write_md(items, path):
    by_tier = collections.Counter(n["tier"] for n in items)
    L = ["# Your Arsenal - what you have and when to use it",
         f"_Auto-generated {datetime.datetime.now().isoformat(timespec='seconds')} - {len(items)} tools "
         f"({by_tier.get('route', 0)} core / {by_tier.get('catalog', 0)} catalog / {by_tier.get('lite', 0)} long-tail)._",
         ""]
    for tier, head in (("route", "## Core (daily drivers)"),
                       ("catalog", "## Catalog (useful - ask your agent for them)"),
                       ("lite", "## Long-tail (installed, rarely needed)")):
        group = [n for n in items if n["tier"] == tier]
        if not group:
            continue
        L += [head, ""]
        for n in sorted(group, key=lambda x: (x["kind"], x["id"])):
            off = "offline" if n["offline"] is True else ("partial" if n["offline"] == "partial" else "online")
            L.append(f"### {n['name']}  `{n['kind']}` - {off}, {n['cost']}")
            for k, label in (("what", "What"), ("use_when", "Use when"), ("avoid_when", "Avoid when"),
                             ("example", "Example")):
                if n[k]:
                    L.append(f"- **{label}:** {n[k]}")
            if n["pairs_with"]:
                L.append(f"- **Pairs with:** {', '.join(map(str, n['pairs_with']))}")
            L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def main():
    raw, warns, nfiles = load_entries()
    seen, items, dups = set(), [], []
    for src, e in raw:
        n = normalize(e)
        key = n["id"].lower()
        if key in seen:
            dups.append(f"{key} (dup in {src}, kept first)")
            continue
        seen.add(key)
        items.append(n)

    qual = list(warns)
    for n in items:
        miss = [f for f in ("what", "use_when", "avoid_when", "tier") if not n.get(f)]
        if miss:
            qual.append(f"{n['id']}: missing {miss}")
    if dups:
        qual.append("--- DUPS ---")
        qual.extend(dups)

    by_tier = collections.Counter(n["tier"] for n in items)
    by_kind = collections.Counter(n["kind"] for n in items)
    payload = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "count": len(items), "by_tier": dict(by_tier), "by_kind": dict(by_kind),
        "items": sorted(items, key=lambda x: (x["tier"] != "route", x["kind"], x["id"])),
    }
    with open(work_path("arsenal.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    write_md(payload["items"], work_path("ARSENAL.md"))
    with open(work_path("quality-report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(qual) + "\n" if qual else "clean - no warnings\n")

    print(f"batch files: {nfiles} | entries loaded: {len(raw)} | unique: {len(items)} | dups: {len(dups)}")
    print(f"by_tier: {dict(by_tier)} | by_kind: {dict(by_kind)}")
    print(f"quality warnings: {len(qual)}")
    print("wrote: arsenal.json, ARSENAL.md, quality-report.txt")


if __name__ == "__main__":
    main()
