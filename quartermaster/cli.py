# -*- coding: utf-8 -*-
"""Command-line front ends. Each main(argv=None, ...) parses its arguments, runs one
pipeline step and prints the result; the top-level scripts only call these.

Every main takes `argv` (default sys.argv[1:]); the ones that embed take `embed` (any
embedder, see embedder.py; default: Ollama from the config), so tests and other callers
run them in-process with no server.
"""
import argparse
import datetime
import os
import sys

from . import catalog_file, config, index, inventory, pipeline, workspace
from .embedder import OllamaEmbedder
from .entry import Entry, offline_label
from .workspace import Workspace

# query exit codes, one meaning each (SKILL.md maps each to one action)
EXIT_OK = 0
EXIT_USAGE = 1
EXIT_EMBEDDING_DOWN = 2   # no embedding server answered; arsenal.json is fine
EXIT_NO_CATALOG = 3       # no readable arsenal.json in the work dir
EXIT_INDEX_STALE = 4      # index missing, or built with another model or dimension

STALE_AFTER_DAYS = 14


def _utf8():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def _setup(c=None):
    _utf8()
    c = c or config.cfg()
    return c, Workspace.from_config(c)


# --- enumerate ----------------------------------------------------------------------

def enumerate_main(argv=None):
    """Scan installed tools into <work_dir>/arsenal_items.json. Read-only on ~/.claude."""
    argparse.ArgumentParser(prog="enumerate_arsenal.py", description=enumerate_main.__doc__).parse_args(argv)
    c, ws = _setup()
    try:
        r = pipeline.enumerate_live(c, ws)
    except inventory.InventoryError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"WROTE {r.path}")
    print("counts:", r.counts, "total:", len(r.items))
    return 0


# --- assemble -----------------------------------------------------------------------

def assemble_main(argv=None):
    """Merge <work_dir>/entries/batch-*.json into arsenal.json, ARSENAL.md and
    quality-report.txt. First-loaded entry wins per (kind, id), so deep entries shadow
    the batch-zz-stubs.json placeholders."""
    argparse.ArgumentParser(prog="assemble_catalog.py", description=assemble_main.__doc__).parse_args(argv)
    _, ws = _setup()
    r = pipeline.assemble(ws)
    print(r.summary())
    print(f"by_tier: {r.by_tier} | by_kind: {r.by_kind}")
    print(f"quality warnings: {r.warnings}")
    print(f"wrote: {workspace.CATALOG}, {workspace.CATALOG_MD}, {workspace.QUALITY}")
    return 0


# --- build_index --------------------------------------------------------------------

def build_index_main(argv=None, embed=None):
    """Embed every catalog entry with the configured model into the semantic index
    (arsenal_index.npz + arsenal_index.meta.json). Needs numpy and a running Ollama."""
    argparse.ArgumentParser(prog="build_index.py", description=build_index_main.__doc__).parse_args(argv)
    c, ws = _setup()
    embed = embed or OllamaEmbedder.from_config(c)
    try:
        _, entries = catalog_file.parse(ws.path(workspace.CATALOG))
        print(f"embedding {len(index.indexed(entries))} entries via {embed.model} ...")
        info = index.build(ws, entries, embed)
    except ImportError:
        print("numpy is missing: pip install -r requirements.txt", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError) as e:
        print(f"build_index FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print(f"wrote {workspace.INDEX_VECTORS} ({info.count}x{info.dim}) + meta")
    return 0


# --- regen --------------------------------------------------------------------------

def regen_main(argv=None, embed=None):
    """Diff the live inventory against the studied catalog. Writes regen_plan.json, and
    study_queue.json while any tool waits for study. Exit 0 ok | 1 the scan failed
    (nothing changed) | 4 the catalog step finished but the index build failed."""
    ap = argparse.ArgumentParser(prog="regen_arsenal.py", description=regen_main.__doc__)
    ap.add_argument("--prune", action="store_true",
                    help="drop uninstalled tools from arsenal.json (.bak kept); models are never pruned")
    ap.add_argument("--force-prune", action="store_true",
                    help="prune even when the mass-prune guard refuses")
    ap.add_argument("--rebuild-index", action="store_true", help="rebuild the semantic index")
    a = ap.parse_args(argv)
    c, ws = _setup()
    r = pipeline.regen(c, ws, prune=a.prune, force_prune=a.force_prune,
                       rebuild_index=a.rebuild_index, embed=embed)
    print("\n".join(r.lines()))
    return r.status


# --- weekly -------------------------------------------------------------------------

def weekly_main(argv=None, embed=None):
    """The zero-LLM self-maintenance run: diff, refresh stubs, assemble, prune, rebuild
    the index, optional copy. Exit 0 ok | 1 a step failed | 4 the catalog is fresh but
    the index build failed (logged as INDEX STALE)."""
    argparse.ArgumentParser(prog="weekly.py", description=weekly_main.__doc__).parse_args(argv)
    c, ws = _setup()
    return pipeline.weekly(c, ws, embed).status


# --- query --------------------------------------------------------------------------

def _catalog_age(generated):
    try:
        return datetime.datetime.now() - datetime.datetime.fromisoformat(generated)
    except (TypeError, ValueError):
        return None


def fmt(entry, sim=None):
    head = f"## {entry['name']}  `{entry['kind']}` / {entry['tier']}"
    if sim is not None:
        head += f"  (match {sim:.2f})"
    lines = [head, f"_{offline_label(entry.get('offline'))}, {entry.get('cost') or 'cost unknown'}_"]
    if entry.get("kind") == "skill":
        lines.append(f"- **Invoke:** `/{index.invoke_name(Entry.from_dict(entry))}`")
    for k, label in (("what", "What"), ("use_when", "Use when"), ("avoid_when", "Avoid when"),
                     ("example", "Example")):
        if entry.get(k):
            lines.append(f"- **{label}:** {entry[k]}")
    for k, label in (("pairs_with", "Pairs with"), ("triggers", "Triggers")):
        if entry.get(k):
            lines.append(f"- **{label}:** {', '.join(map(str, entry[k]))}")
    return "\n".join(lines)


def _no_catalog(ws, err):
    print(f"CATALOG-UNAVAILABLE: {err}", file=sys.stderr)
    print(f"No readable {workspace.CATALOG} in the work dir ({ws.dir}). Check "
          f"QUARTERMASTER_CONFIG / the config's work_dir, and run assemble_catalog.py first.")
    legacy = os.path.join(config.ENGINE_DIR, "data", workspace.CATALOG)
    if os.path.isfile(legacy) and os.path.abspath(legacy) != ws.path(workspace.CATALOG):
        print(f"Found a catalog from an older version at {legacy}: move the folder "
              f"{os.path.dirname(legacy)} to {ws.dir}, or set work_dir to it.")
    return EXIT_NO_CATALOG


def _stale(ws, why):
    print(f"INDEX-STALE: {why}", file=sys.stderr)
    print("The semantic index is missing or out of date. Rebuild it with "
          "`regen_arsenal.py --rebuild-index`; meanwhile read arsenal.json in the work dir "
          f"directly: {ws.path(workspace.CATALOG)}")
    return EXIT_INDEX_STALE


def query_main(argv=None, embed=None):
    """Answer "what do I have for X?" from the catalog. Exit 0 ok | 1 usage |
    2 EMBEDDING-UNAVAILABLE (read arsenal.json directly) | 3 CATALOG-UNAVAILABLE |
    4 INDEX-STALE (rebuild the index; meanwhile read arsenal.json)."""
    ap = argparse.ArgumentParser(prog="query_arsenal.py", description=query_main.__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="*", help="the need, in plain words")
    ap.add_argument("--k", type=int, default=5, help="max results (default 5)")
    ap.add_argument("--explain", metavar="ID", help="show one tool's full entry")
    ap.add_argument("--sims", action="store_true",
                    help="print raw similarities (to calibrate query.min_sim)")
    a = ap.parse_args(argv)
    c, ws = _setup()

    try:
        cat = ws.read_json(workspace.CATALOG)
        items = {(i.get("kind", ""), i["id"]): i for i in cat["items"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        return _no_catalog(ws, e)
    generated = cat.get("generated")

    if a.explain:
        hits = [v for (_, i), v in items.items() if i == a.explain]
        if not hits:
            probe = a.explain.lower()
            hits = [v for (_, i), v in items.items()
                    if probe in i.lower() or probe in str(v.get("name", "")).lower()]
            if len(hits) > 1:
                print(f"ambiguous '{a.explain}' - candidates: "
                      + ", ".join(f"{h['id']} ({h.get('kind', '?')})" for h in hits[:10]))
                return EXIT_OK
        if not hits:
            print(f"no tool with id like '{a.explain}' in the catalog ({len(items)} items)")
            return EXIT_OK
        print("\n\n".join(fmt(e) for e in hits))  # one id can name a plugin and its skill
        return EXIT_OK

    q = " ".join(a.query).strip()
    if not q:
        ap.print_usage()
        return EXIT_USAGE
    try:
        import numpy  # noqa: F401
    except ImportError:
        print("numpy is missing: pip install -r requirements.txt (--explain works without it)",
              file=sys.stderr)
        return EXIT_USAGE

    embed = embed or OllamaEmbedder.from_config(c)
    instruction = c.get("embed", {}).get("query_instruction")
    text = f"Instruct: {instruction}\nQuery: {q}" if instruction else q
    s = index.search(ws, text, embed)
    if s.status == index.STALE:
        return _stale(ws, s.reason)
    if s.status == index.EMBEDDING_DOWN:
        print(f"EMBEDDING-UNAVAILABLE: {s.reason}", file=sys.stderr)
        print(f"Semantic search is down ({s.hint}). Degrade: read "
              f"arsenal.json in the work dir directly: {ws.path(workspace.CATALOG)}")
        return EXIT_EMBEDDING_DOWN

    if a.sims:
        for score, kind, iid in s.ranked[: max(a.k, 15)]:
            print(f"{score:.4f}  {kind}/{iid}")
        return EXIT_OK

    min_sim = c.get("query", {}).get("min_sim", 0.60)
    out = []
    for score, kind, iid in s.ranked:
        if score < min_sim or len(out) >= a.k:
            break
        e = items.get((kind, iid))
        if e:
            out.append(fmt(e, score))
    age = _catalog_age(generated)
    note = f"_catalog generated {generated}_"
    if age is not None and age.days > STALE_AFTER_DAYS:
        note += (f"  \n**Catalog is {age.days} days old:** run weekly.py (or regen_arsenal.py) "
                 f"so new and removed tools show up.")
    if not out:
        best = ", ".join(f"{iid} ({score:.2f})" for score, _, iid in s.ranked[:3])
        print(f"No match above {min_sim} for: '{q}'. Nearest (below threshold): {best}.")
        print(note)
        return EXIT_OK
    print(f"# Arsenal matches for: {q}\n{note}\n")
    print("\n\n".join(out))
    return EXIT_OK
