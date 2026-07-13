# -*- coding: utf-8 -*-
"""Enumerate the LIVE arsenal from disk + optional sources into arsenal_items.json.

Sources (all configured in quartermaster.config.json under "scan"):
  skill_roots    - directories walked recursively for SKILL.md files
  agents_dir     - directory of agent .md files (optional)
  claude_settings- path to a Claude settings.json; enabledPlugins become plugin items (optional)
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


def frontmatter(path):
    name = desc = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read(4000)
    except OSError:
        return name, desc
    m = re.search(r"^---\s*(.*?)\s*---", txt, re.S | re.M)
    block = m.group(1) if m else txt
    n = re.search(r"^name:\s*(.+)$", block, re.M)
    d = re.search(r"^description:\s*(.+)$", block, re.M)
    if n:
        name = n.group(1).strip().strip("\"'")
    if d:
        desc = d.group(1).strip().strip("\"'")
    return name, desc


def find_skills(roots):
    seen = {}
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for p in glob.glob(os.path.join(root, "**", "SKILL.md"), recursive=True):
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
    items += find_skills(scan.get("skill_roots", []))
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
