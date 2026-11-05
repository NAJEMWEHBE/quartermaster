# -*- coding: utf-8 -*-
"""Enumerate the LIVE arsenal from disk + optional sources into arsenal_items.json.

Sources (all configured in quartermaster.config.json under "scan"):
  skill_roots    - directories walked recursively for SKILL.md files
  agents_dir     - directory of agent .md files (optional)
  claude_settings- path to a Claude settings.json; enabledPlugins become plugin items (optional)
  marketplaces_registry - path to known_marketplaces.json; skills under the sibling
                   marketplaces/ dir that belong to no registered marketplace are
                   dropped as orphan clones (optional; see registry_gate)
  ollama_models  - true to include `ollama list` output as model items (optional)
Read-only. No secrets read or emitted.
"""
import collections
import glob
import json
import os
import re
import subprocess
import sys

from config import cfg, work_path


_FRONTMATTER = re.compile(r"^---[ \t]*\n(.*?)^---[ \t]*$", re.S | re.M)
_TOP_KEY = re.compile(r"^([A-Za-z_][\w-]*):(?:[ \t]+(.*?))?[ \t]*$")
_BLOCK_HEADER = re.compile(r"^([|>])[0-9+-]*(?:[ \t]+#.*)?$")
_ESCAPES = {"n": "\n", "t": "\t"}


def _block_scalar(style, lines):
    """A YAML literal (|) or folded (>) block: drop the common indent, then keep the
    line breaks (literal) or fold single breaks into spaces (folded)."""
    body = list(lines)
    while body and not body[-1].strip():
        body.pop()
    indent = min((len(l) - len(l.lstrip(" ")) for l in body if l.strip()), default=0)
    body = [l[indent:] for l in body]
    if style == "|":
        return "\n".join(body)
    paras, cur = [], []
    for l in body + [""]:
        if l.strip():
            cur.append(l.strip())
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    return "\n".join(paras)


def _scalar(first, more):
    """One top-level YAML scalar. `first` is the text after `key:`, `more` its indented
    continuation lines. Handles plain, single- and double-quoted, and block (| >) scalars."""
    if _BLOCK_HEADER.match(first):
        return _block_scalar(first[0], more)
    flat = " ".join([first] + [l.strip() for l in more if l.strip()]).strip()
    if flat.startswith('"'):
        m = re.match(r'"((?:[^"\\]|\\.)*)"', flat)
        inner = m.group(1) if m else flat[1:]
        return re.sub(r"\\(.)", lambda e: _ESCAPES.get(e.group(1), e.group(1)), inner)
    if flat.startswith("'"):
        m = re.match(r"'((?:[^']|'')*)'", flat)
        return (m.group(1) if m else flat[1:]).replace("''", "'")
    return flat


def _top_level_scalars(block):
    """Top-level `key: value` pairs of a frontmatter block: a small YAML subset, enough
    for SKILL.md and agent files, with no PyYAML dependency. First occurrence wins."""
    out, lines, i = {}, block.splitlines(), 0
    while i < len(lines):
        m = _TOP_KEY.match(lines[i])
        i += 1
        if not m:
            continue
        more = []
        while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
            more.append(lines[i])
            i += 1
        out.setdefault(m.group(1), _scalar(m.group(2) or "", more))
    return out


def frontmatter(path):
    """(name, description) from a markdown file's YAML frontmatter; ("", "") if unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read(16000).lstrip("﻿")
    except OSError:
        return "", ""
    m = _FRONTMATTER.search(txt)
    fields = _top_level_scalars(m.group(1) if m else txt)
    return fields.get("name", "").strip(), fields.get("description", "").strip()


def _norm(p):
    # realpath, not abspath: a junction/symlinked marketplace must compare equal to the
    # walked path that reached it. Both sides go through here, so it stays symmetric.
    return os.path.normcase(os.path.realpath(os.path.expanduser(p)))


def _under(path, base):
    """True if `path` is inside `base` (or equal). Both already normcased/abs."""
    return path == base or path.startswith(base + os.sep)


def _gate_off(why):
    # Degraded operation is always announced (same contract as ollama_models): a silently
    # disabled gate re-admits orphans, and the NEXT harness cleanup of those orphans reads
    # as a real uninstall - i.e. exactly the prune-collapse this gate exists to prevent.
    print(f"WARNING: marketplace orphan gate OFF ({why})", file=sys.stderr)
    return lambda p: True


def registry_gate(registry_path):
    """Build a keep-predicate that drops skills sitting inside the plugins `marketplaces`
    directory that belong to NO registered marketplace. Orphan/temp clones (e.g. a
    leftover temp_* dir absent from known_marketplaces.json) are swept in by a broad
    `~/.claude/plugins/marketplaces` scan root but must not enter the catalog - they read
    as live inventory the moment they appear and as a phantom uninstall the moment the
    harness cleans them.

    The gated zone is the `marketplaces` dir sitting BESIDE the registry file - never the
    parent of each registered installLocation. Directory-source marketplaces may be
    registered from anywhere on disk (a live entry here points at F:\\ai\\dir-marketplace),
    so parent-inference promoted whole project trees into gate zones: every skill in such
    a tree outside the one registered dir vanished from LIVE and became prune bait.

    Fails OPEN (predicate always True, warning on stderr) whenever the registry is unset,
    unreadable or malformed, so this only ever removes provable orphans.

    2026-07-19: widening the scan root to plugins/marketplaces swept in temp_1783969352387
    (improve-react, react-doctor) - this gate is the structural fix for that class."""
    path = os.path.expanduser(registry_path)
    try:
        with open(path, encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError) as e:
        # ValueError covers both JSONDecodeError and UnicodeDecodeError (a registry saved
        # as UTF-16 raises the latter, which is NOT a JSONDecodeError).
        return _gate_off(f"{type(e).__name__} reading {path}")
    if not isinstance(reg, dict):
        return _gate_off(f"{path} is a JSON {type(reg).__name__}, expected an object")
    allowed = {_norm(v["installLocation"]) for v in reg.values()
               if isinstance(v, dict) and isinstance(v.get("installLocation"), str)
               and v["installLocation"]}
    zone = _norm(os.path.join(os.path.dirname(path), "marketplaces"))
    if not allowed:
        return _gate_off(f"no usable installLocation in {path}")
    if not os.path.isdir(zone):
        return _gate_off(f"no marketplaces dir at {zone}")

    def keep(p):
        p = _norm(p)
        return not _under(p, zone) or any(_under(p, a) for a in allowed)

    return keep


def find_skills(roots, keep=None):
    keep = keep or (lambda p: True)
    seen = {}
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, "**", "SKILL.md"), recursive=True):
            if not keep(p):
                continue
            name, desc = frontmatter(p)
            key = (name or os.path.basename(os.path.dirname(p))).lower()
            if key not in seen:  # first root wins on duplicates
                seen[key] = {"kind": "skill", "name": name or key, "desc": desc[:240], "path": p}
    return list(seen.values())


def enabled_plugins(settings_path):
    try:
        with open(os.path.expanduser(settings_path), encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for k, v in s.get("enabledPlugins", {}).items():
        if v is True:
            name, _, mkt = k.partition("@")
            out.append({"kind": "plugin", "name": name, "marketplace": mkt})
    return out


def agents(agents_dir):
    out = []
    d = os.path.expanduser(agents_dir)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".md"):
                name, desc = frontmatter(os.path.join(d, f))
                out.append({"kind": "agent", "name": name or f[:-3], "desc": desc[:240],
                            "path": os.path.join(d, f)})
    return out


def local_mcp(mcp_dir):
    """Enumerate locally-installed MCP servers as kind='mcp' items. Each immediate
    subdirectory of mcp_dir is one server. Config-driven (scan.mcp_dir); returns []
    when unset so no personal path is hardcoded."""
    out = []
    if not mcp_dir:
        return out
    d = os.path.expanduser(mcp_dir)
    if os.path.isdir(d):
        for x in sorted(os.listdir(d)):
            if os.path.isdir(os.path.join(d, x)):
                out.append({"kind": "mcp", "name": x, "scope": "local"})
    return out


def ollama_models():
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=20)
        return [{"kind": "model", "name": l.split()[0], "engine": "ollama-local"}
                for l in r.stdout.splitlines()[1:] if l.strip()]
    except (OSError, subprocess.SubprocessError) as e:
        print(f"WARNING: ollama list failed ({e}); skipping model enumeration", file=sys.stderr)
        return []


def main():
    scan = cfg().get("scan", {})
    items = []
    keep = registry_gate(scan["marketplaces_registry"]) if scan.get("marketplaces_registry") else None
    items += find_skills(scan.get("skill_roots", []), keep)
    if scan.get("claude_settings"):
        items += enabled_plugins(scan["claude_settings"])
    if scan.get("agents_dir"):
        items += agents(scan["agents_dir"])
    if scan.get("mcp_dir"):
        items += local_mcp(scan["mcp_dir"])
    if scan.get("ollama_models"):
        items += ollama_models()

    by_kind = collections.Counter(i["kind"] for i in items)
    out = work_path("arsenal_items.json")
    os.makedirs(cfg()["work_dir"], exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"items": items, "counts": dict(by_kind), "total": len(items)}, f,
                  indent=2, ensure_ascii=False)
    print(f"WROTE {out}")
    print("counts:", dict(by_kind), "total:", len(items))


if __name__ == "__main__":
    main()
