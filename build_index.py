# -*- coding: utf-8 -*-
"""Build the semantic index over the catalog's skill entries.

Embeds each skill's meaning (via entry.embed_text) with the configured Ollama model,
writes arsenal_index.npz (vectors only, no pickle) + arsenal_index.meta.json.
Build-time only; query_arsenal.py degrades gracefully when the index or Ollama is missing.
Requires numpy.
"""
import datetime
import json

import numpy as np

import catalog_file
from config import cfg, embed, work_path
from entry import embed_text


def invoke_name(entry):
    """Best 'invoke this' label for meta['names']: prefer a plugin:skill-style name
    (one containing ':'), else the slug id, else the display name."""
    name = str(entry.name or "").strip()
    iid = str(entry.id or "").strip()
    if ":" in name:
        return name
    return iid or name


def main():
    _, entries = catalog_file.parse(work_path("arsenal.json"))
    items = [e for e in entries if e.kind == "skill"]
    if not items:
        print("no skill entries in arsenal.json - nothing to index")
        return 1
    print(f"embedding {len(items)} skill entries via {cfg().get('embed', {}).get('model')} ...")
    texts = [embed_text(e) for e in items]
    vecs = []
    B = 64
    for s in range(0, len(texts), B):
        vecs.extend(embed(texts[s:s + B]))
    arr = np.asarray(vecs, dtype=np.float32)
    np.savez(work_path("arsenal_index.npz"), vecs=arr)
    meta = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": cfg().get("embed", {}).get("model"), "dim": int(arr.shape[1]),
            "count": len(items), "source": "arsenal.json",
            "ids": [e.id for e in items], "names": [invoke_name(e) for e in items],
            "tiers": [str(e.tier) for e in items]}
    with open(work_path("arsenal_index.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(f"wrote arsenal_index.npz ({arr.shape[0]}x{arr.shape[1]}) + meta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
