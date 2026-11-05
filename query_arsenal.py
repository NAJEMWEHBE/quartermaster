# -*- coding: utf-8 -*-
"""Answer "what do I have for X?" from the catalog.

Modes:
  python query_arsenal.py "reviewing a pull request"     # semantic top-k
  python query_arsenal.py --k 8 "image to 3d"
  python query_arsenal.py --explain <tool-id>            # single-tool deep view
  python query_arsenal.py --sims "query"                 # raw similarities (threshold calibration)

Exit codes, one meaning each:
  0 ok
  1 usage error
  2 EMBEDDING-UNAVAILABLE  no embedding server answered; arsenal.json is fine, read it directly
  3 CATALOG-UNAVAILABLE    no readable arsenal.json in the work dir (config or setup problem)
  4 INDEX-STALE            the semantic index is missing or was built with another model;
                           run regen_arsenal.py --rebuild-index, meanwhile read arsenal.json
The min_sim threshold lives in the config ("query": {"min_sim": ...}); calibrate per embed
model with --sims (compare a junk query's top score vs real queries').
"""
import argparse
import json
import sys

from config import cfg, embed, work_path
from entry import offline_label

sys.stdout.reconfigure(encoding="utf-8")

EXIT_EMBEDDING_DOWN = 2
EXIT_NO_CATALOG = 3
EXIT_INDEX_STALE = 4


def _stale(why):
    print(f"INDEX-STALE: {why}", file=sys.stderr)
    print("The semantic index is missing or out of date. Rebuild it with "
          "`regen_arsenal.py --rebuild-index`; meanwhile read arsenal.json in the work dir "
          f"directly: {work_path('arsenal.json')}")
    return EXIT_INDEX_STALE


def load_catalog():
    """{(kind, id): item}. Ids are unique per kind only: a plugin `foo` and its skill
    `foo` are two entries."""
    with open(work_path("arsenal.json"), encoding="utf-8") as f:
        cat = json.load(f)
    return {(i.get("kind", ""), i["id"]): i for i in cat["items"]}


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

    try:
        items = load_catalog()
    except (OSError, json.JSONDecodeError) as e:
        print(f"CATALOG-UNAVAILABLE: {e}", file=sys.stderr)
        print("No readable arsenal.json in the work dir. Check QUARTERMASTER_CONFIG / the "
              "config's work_dir, and run assemble_catalog.py first.")
        return EXIT_NO_CATALOG
    min_sim = cfg().get("query", {}).get("min_sim", 0.60)

    if args.explain:
        hits = [v for (_, i), v in items.items() if i == args.explain]
        if not hits:
            probe = args.explain.lower()
            hits = [v for (_, i), v in items.items()
                    if probe in i.lower() or probe in str(v.get("name", "")).lower()]
            if len(hits) > 1:
                print(f"ambiguous '{args.explain}' - candidates: "
                      + ", ".join(f"{h['id']} ({h.get('kind', '?')})" for h in hits[:10]))
                return 0
        if not hits:
            print(f"no tool with id like '{args.explain}' in the catalog ({len(items)} items)")
            return 0
        print("\n\n".join(fmt(e) for e in hits))  # one id can name a plugin and its skill
        return 0

    q = " ".join(args.query).strip()
    if not q:
        print("usage: query_arsenal.py <plain words need> | --explain <id>")
        return 1

    try:
        import numpy as np
    except ImportError:
        print("numpy is missing: pip install -r requirements.txt (--explain works without it)",
              file=sys.stderr)
        return 1
    model = cfg().get("embed", {}).get("model")
    try:
        with open(work_path("arsenal_index.meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        vecs = np.load(work_path("arsenal_index.npz"), allow_pickle=False)["vecs"]
        if vecs.ndim != 2 or vecs.shape[0] != len(meta["ids"]):
            raise ValueError(f"index holds {vecs.shape} vectors for {len(meta['ids'])} ids")
    except (OSError, ValueError, KeyError) as e:
        return _stale(f"no usable index ({type(e).__name__}: {e})")
    if meta.get("model") != model:
        # A model swap that keeps the dimension would rank silently wrong, so the
        # index's model must be the configured one, checked before any embedding.
        return _stale(f"index built with {meta.get('model')!r}, config uses {model!r}")

    try:
        qv = np.asarray(embed([q]), dtype=vecs.dtype)
    except (OSError, ValueError, RuntimeError) as e:  # URLError/timeouts are OSError
        print(f"EMBEDDING-UNAVAILABLE: {e}", file=sys.stderr)
        if getattr(e, "code", None) == 404:  # urllib HTTPError: the server is up, the model isn't
            why = f"the embedding model {model!r} is not on the server; run `ollama pull {model}`"
        else:
            why = "no embedding server answered"
        print(f"Semantic search is down ({why}). Degrade: read "
              f"arsenal.json in the work dir directly: {work_path('arsenal.json')}")
        return EXIT_EMBEDDING_DOWN
    if qv.ndim != 2 or qv.shape != (1, vecs.shape[1]):
        return _stale(f"query embedding has shape {qv.shape}, index rows have {vecs.shape[1]} dims")
    # Defensive query-time normalization: renormalize the query vector and divide by
    # fresh row norms (zero-guarded) rather than trusting build-time normalization.
    qv = qv[0] / (np.linalg.norm(qv[0]) or 1.0)
    norms = np.linalg.norm(vecs, axis=1)
    norms[norms == 0] = 1.0
    sims = (vecs @ qv) / norms

    order = sims.argsort()[::-1]
    ids = meta["ids"]
    kinds = meta.get("kinds") or ["skill"] * len(ids)  # older indexes held skills only

    if args.sims:
        for i in order[: max(args.k, 15)]:
            print(f"{sims[i]:.4f}  {ids[i]}")
        return 0

    out = []
    for i in order:
        if sims[i] < min_sim or len(out) >= args.k:
            break
        e = items.get((kinds[i], ids[i]))
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
