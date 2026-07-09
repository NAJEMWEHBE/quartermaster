# -*- coding: utf-8 -*-
"""Build the semantic index over the catalog's skill entries.

Embeds name + triggers + use_when + what per skill via the configured Ollama model,
writes arsenal_index.npz (vectors only, no pickle) + arsenal_index.meta.json.
Build-time only; query_arsenal.py degrades gracefully when the index or Ollama is missing.
Requires numpy.
"""
import datetime
import json

import numpy as np

from config import cfg, embed, work_path


def embed_text(item):
    parts = [item.get("name", ""), " ".join(item.get("triggers", [])),
             item.get("use_when", ""), item.get("what", "")]
    return ". ".join(p for p in parts if p)


def main():
    cat = json.load(open(work_path("arsenal.json"), encoding="utf-8"))
    items = [i for i in cat["items"] if i.get("kind") == "skill"]
    if not items:
        print("no skill entries in arsenal.json - nothing to index")
        return 1
    print(f"embedding {len(items)} skill entries via {cfg().get('embed', {}).get('model')} ...")
    texts = [embed_text(i) for i in items]
    vecs = []
    B = 64
    for s in range(0, len(texts), B):
        vecs.extend(embed(texts[s:s + B]))
    arr = np.asarray(vecs, dtype=np.float32)
    np.savez(work_path("arsenal_index.npz"), vecs=arr)
    meta = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": cfg().get("embed", {}).get("model"), "dim": int(arr.shape[1]),
            "count": len(items), "source": "arsenal.json",
            "ids": [i["id"] for i in items], "names": [i["name"] for i in items],
            "tiers": [i["tier"] for i in items]}
    with open(work_path("arsenal_index.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    print(f"wrote arsenal_index.npz ({arr.shape[0]}x{arr.shape[1]}) + meta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
