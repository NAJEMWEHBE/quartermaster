# -*- coding: utf-8 -*-
"""Owner of the semantic index: building it and searching it.

    build(ws, entries, embed)       -> IndexInfo      (raises on embedder failure)
    search(ws, query, embed)        -> Search         (never raises for the cases below)

A Search has one status: OK, EMBEDDING_DOWN (no embedder answered), or STALE (no usable
index, or one built with another model or dimension). The embedder is injected (see
embedder.py), and its `model` must match the one the index was built with.
Needs numpy; imported lazily so catalog-only commands work without it.
"""
import datetime
from dataclasses import dataclass, field

from . import workspace
from .entry import embed_text

OK = "ok"
EMBEDDING_DOWN = "embedding-down"
STALE = "stale"

BATCH = 64


def invoke_name(entry):
    """Best 'invoke this' label: a plugin:skill-style name (one containing ':'), else the
    id, else the display name."""
    name = str(entry.name or "").strip()
    iid = str(entry.id or "").strip()
    if ":" in name:
        return name
    return iid or name


def indexed(entries):
    """The entries the index covers: every kind (skills, plugins, agents, MCP servers,
    models), so "which agent reviews code" can match as well as a skill can."""
    return list(entries)


@dataclass
class IndexInfo:
    count: int
    dim: int
    model: str


@dataclass
class Search:
    status: str
    ranked: list = field(default_factory=list)  # [(score, kind, id)], best first
    reason: str = ""
    hint: str = ""   # EMBEDDING_DOWN: what to do about it


def build(ws, entries, embed):
    """Embed `entries` (see indexed()) and write the index files atomically: vectors
    first, then meta, so a query in between sees a count mismatch and reports STALE
    instead of ranking against the wrong ids. Raises ValueError when there is nothing
    to index; embedder errors propagate."""
    import numpy as np
    items = indexed(entries)
    if not items:
        raise ValueError("the catalog has no entries - nothing to index")
    texts = [embed_text(e) for e in items]
    vecs = []
    for s in range(0, len(texts), BATCH):
        vecs.extend(embed(texts[s:s + BATCH]))
    arr = np.asarray(vecs, dtype=np.float32)
    workspace.write_with(ws.path(workspace.INDEX_VECTORS), lambda f: np.savez(f, vecs=arr), mode="wb")
    meta = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "model": embed.model, "dim": int(arr.shape[1]),
            "count": len(items), "source": workspace.CATALOG,
            "ids": [e.id for e in items], "kinds": [e.kind for e in items],
            "names": [invoke_name(e) for e in items],
            "tiers": [str(e.tier) for e in items]}
    ws.write_json(workspace.INDEX_META, meta, indent=1)
    return IndexInfo(len(items), int(arr.shape[1]), embed.model)


def search(ws, query, embed):
    """Rank every indexed entry against `query` by cosine similarity."""
    import numpy as np
    try:
        meta = ws.read_json(workspace.INDEX_META)
        vecs = np.load(ws.path(workspace.INDEX_VECTORS), allow_pickle=False)["vecs"]
        if vecs.ndim != 2 or vecs.shape[0] != len(meta["ids"]):
            raise ValueError(f"index holds {vecs.shape} vectors for {len(meta['ids'])} ids")
    except (OSError, ValueError, KeyError) as e:
        return Search(STALE, reason=f"no usable index ({type(e).__name__}: {e})")
    if meta.get("model") != embed.model:
        # A model swap that keeps the dimension would rank silently wrong, so the
        # index's model must be the embedder's, checked before any embedding.
        return Search(STALE, reason=f"index built with {meta.get('model')!r}, "
                                    f"config uses {embed.model!r}")
    try:
        qv = np.asarray(embed([query]), dtype=vecs.dtype)
    except (OSError, ValueError, RuntimeError) as e:  # URLError/timeouts are OSError
        if getattr(e, "code", None) == 404:  # urllib HTTPError: the server is up, the model isn't
            hint = f"the embedding model {embed.model!r} is not on the server; run `ollama pull {embed.model}`"
        else:
            hint = "no embedding server answered"
        return Search(EMBEDDING_DOWN, reason=str(e), hint=hint)
    if qv.ndim != 2 or qv.shape != (1, vecs.shape[1]):
        return Search(STALE, reason=f"query embedding has shape {qv.shape}, "
                                    f"index rows have {vecs.shape[1]} dims")
    # Defensive query-time normalization: renormalize the query vector and divide by
    # fresh row norms (zero-guarded) rather than trusting build-time normalization.
    qv = qv[0] / (np.linalg.norm(qv[0]) or 1.0)
    norms = np.linalg.norm(vecs, axis=1)
    norms[norms == 0] = 1.0
    sims = (vecs @ qv) / norms
    kinds = meta.get("kinds") or ["skill"] * len(meta["ids"])  # older indexes: skills only
    order = sims.argsort()[::-1]
    return Search(OK, [(float(sims[i]), kinds[i], meta["ids"][i]) for i in order])
