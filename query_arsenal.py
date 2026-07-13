# -*- coding: utf-8 -*-
"""Answer "what do I have for X?" from the catalog.

Modes:
  python query_arsenal.py "reviewing a pull request"     # semantic top-k
  python query_arsenal.py --k 8 "image to 3d"
  python query_arsenal.py --explain <tool-id>            # single-tool deep view
  python query_arsenal.py --sims "query"                 # raw similarities (threshold calibration)

Exit codes: 0 ok | 2 embedding unavailable (degrade: read arsenal.json directly) | 1 error.
The min_sim threshold lives in the config ("query": {"min_sim": ...}); calibrate per embed
model with --sims (compare a junk query's top score vs real queries').
"""
import argparse
import json
import sys

from config import cfg, embed, work_path
from entry import offline_label

sys.stdout.reconfigure(encoding="utf-8")


def load_catalog():
    cat = json.load(open(work_path("arsenal.json"), encoding="utf-8"))
    return {i["id"]: i for i in cat["items"]}


def fmt(entry, sim=None):
    head = f"## {entry['name']}  `{entry['kind']}` / {entry['tier']}"
    if sim is not None:
        head += f"  (match {sim:.2f})"
    off = offline_label(entry.get("offline"))
    lines = [head, f"_{off}, {entry.get('cost', '?')}_"]
    for k, label in (("what", "What"), ("use_when", "Use when"), ("avoid_when", "Avoid when"),
                     ("example", "Example")):
        if entry.get(k):
            lines.append(f"- **{label}:** {entry[k]}")
    for k, label in (("pairs_with", "Pairs with"), ("triggers", "Triggers")):
        if entry.get(k):
            lines.append(f"- **{label}:** {', '.join(map(str, entry[k]))}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="*")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--explain", help="single tool id to explain")
    ap.add_argument("--sims", action="store_true", help="print raw similarity list")
    args = ap.parse_args()

    items = load_catalog()
    min_sim = cfg().get("query", {}).get("min_sim", 0.60)

    if args.explain:
        e = items.get(args.explain)
        if not e:
            probe = args.explain.lower()
            hits = [v for k, v in items.items() if probe in k or probe in str(v.get("name", "")).lower()]
            if len(hits) == 1:
                e = hits[0]
            elif hits:
                print(f"ambiguous '{args.explain}' - candidates: " + ", ".join(h["id"] for h in hits[:10]))
                return 0
        print(fmt(e) if e else f"no tool with id like '{args.explain}' in the catalog ({len(items)} items)")
        return 0

    q = " ".join(args.query).strip()
    if not q:
        print("usage: query_arsenal.py <plain words need> | --explain <id>")
        return 1

    try:
        import numpy as np
        meta = json.load(open(work_path("arsenal_index.meta.json"), encoding="utf-8"))
        vecs = np.load(work_path("arsenal_index.npz"), allow_pickle=False)["vecs"]
        # Defensive query-time normalization: validate the embedding shape, renormalize
        # the query vector, and divide by fresh row norms (zero-guarded) rather than
        # trusting build-time normalization.
        qv = np.asarray(embed([q]), dtype=vecs.dtype)
        if qv.ndim != 2 or qv.shape[0] != 1:
            raise RuntimeError(f"bad query embedding shape {qv.shape}")
        qv = qv[0]
        qv = qv / (np.linalg.norm(qv) or 1.0)
        norms = np.linalg.norm(vecs, axis=1)
        norms[norms == 0] = 1.0
        sims = (vecs @ qv) / norms
    except Exception as e:
        print(f"EMBEDDING-UNAVAILABLE: {e}", file=sys.stderr)
        print("Semantic search down (Ollama not serving / index missing). "
              "Degrade: read arsenal.json in the work dir directly.")
        return 2

    order = sims.argsort()[::-1]
    ids = meta["ids"]

    if args.sims:
        for i in order[: max(args.k, 15)]:
            print(f"{sims[i]:.4f}  {ids[i]}")
        return 0

    out = []
    for i in order:
        if sims[i] < min_sim or len(out) >= args.k:
            break
        e = items.get(ids[i])
        if e:
            out.append(fmt(e, sims[i]))
    if not out:
        best = ", ".join(f"{ids[i]} ({sims[i]:.2f})" for i in order[:3])
        print(f"No match above {min_sim} for: '{q}'. Nearest (below threshold): {best}. "
              f"The index covers skills only - for other kinds read arsenal.json.")
        return 0
    print(f"# Arsenal matches for: {q}\n")
    print("\n\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
