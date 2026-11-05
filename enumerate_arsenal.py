# -*- coding: utf-8 -*-
"""Enumerate the LIVE arsenal from disk + optional sources into arsenal_items.json.

Sources (all configured in quartermaster.config.json under "scan"):
  skill_roots    - directories walked recursively for SKILL.md files (user skills)
  installed_plugins - path to Claude Code's installed_plugins.json; each enabled plugin's
                   skills are read from its live install dir and named plugin:skill.
                   Skill roots inside that plugins dir are then skipped (optional)
  agents_dir     - directory of agent .md files (optional)
  claude_settings- path to a Claude settings.json; enabledPlugins become plugin items and
                   decide which installed plugins count (optional)
  marketplaces_registry - path to known_marketplaces.json; skills under the sibling
                   marketplaces/ dir that belong to no registered marketplace are
                   dropped as orphan clones (optional; see registry_gate)
  ollama_models  - true to list the models of an already running Ollama server (GET
                   /api/tags on embed.url) as model items; never starts Ollama (optional)
Read-only. No secrets read or emitted.
"""
import collections
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request

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
    registered from anywhere on disk (a live entry here points at F:\\ai\\mcp-wrappers),
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


def _skill_files(root):
    return sorted(glob.glob(os.path.join(root, "**", "SKILL.md"), recursive=True))


def _skill_item(path, plugin=None, marketplace=None):
    """One live skill. `invoke` is how Claude Code calls it (`plugin:skill` for plugin
    skills, the bare name otherwise) and is the skill's identity: two plugins may both
    ship an `access` skill, and those are two different tools."""
    name, desc = frontmatter(path)
    name = name or os.path.basename(os.path.dirname(path))
    item = {"kind": "skill", "name": name, "invoke": f"{plugin}:{name}" if plugin else name}
    if plugin:
        item.update(plugin=plugin, marketplace=marketplace)
    item.update(desc=desc[:240], path=path)
    return item


def find_skills(roots, keep=None):
    """Skills under plain skill roots (e.g. ~/.claude/skills), keyed by their invoke name;
    the first root wins when two roots hold the same skill."""
    keep = keep or (lambda p: True)
    seen = {}
    for root in roots:
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for p in _skill_files(root):
            if keep(p):
                item = _skill_item(p)
                seen.setdefault(item["invoke"].lower(), item)
    return list(seen.values())


def plugin_installs(installed_path):
    """{"plugin@marketplace": installPath} from Claude Code's installed_plugins.json.

    installPath is the one live version dir; the cache keeps older ones beside it. A
    missing file means no plugins (warning). A file that exists but can't be read stops
    the run: silently dropping every plugin skill would read as a mass uninstall."""
    path = os.path.expanduser(installed_path)
    if not os.path.exists(path):
        print(f"WARNING: no installed-plugins file at {path}; no plugin skills listed", file=sys.stderr)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            reg = json.load(f)
    except (OSError, ValueError) as e:
        raise SystemExit(f"ERROR: cannot read {path} ({type(e).__name__}: {e})")
    plugins = reg.get("plugins", reg) if isinstance(reg, dict) else None
    if not isinstance(plugins, dict):
        raise SystemExit(f"ERROR: {path} has no plugins object")
    out = {}
    for key, recs in plugins.items():
        recs = [r for r in (recs if isinstance(recs, list) else [recs])
                if isinstance(r, dict) and isinstance(r.get("installPath"), str)]
        recs.sort(key=lambda r: r.get("scope") != "user")  # user scope first
        live = next((r["installPath"] for r in recs if os.path.isdir(os.path.expanduser(r["installPath"]))), None)
        if live:
            out[key] = os.path.expanduser(live)
    return out


def enabled_plugin_keys(settings_path):
    """The set of "plugin@marketplace" keys enabled in a Claude settings.json, or None
    when the file can't be read (callers then treat every installed plugin as enabled)."""
    path = os.path.expanduser(settings_path)
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        enabled = s.get("enabledPlugins", {})
        return {k for k, v in enabled.items() if v is True}
    except (OSError, ValueError, AttributeError) as e:
        print(f"WARNING: cannot read enabledPlugins from {path} ({type(e).__name__})", file=sys.stderr)
        return None


def plugin_skills(installs, enabled=None):
    """Skills of each installed plugin that is enabled (all installed ones if `enabled`
    is None), read from the plugin's live install dir only."""
    out, seen = [], set()
    for key in sorted(installs):
        if enabled is not None and key not in enabled:
            continue
        plugin, _, mkt = key.partition("@")
        for p in _skill_files(installs[key]):
            item = _skill_item(p, plugin, mkt)
            if item["invoke"].lower() not in seen:
                seen.add(item["invoke"].lower())
                out.append(item)
    return out


def plugin_items(keys):
    out = []
    for k in sorted(keys or ()):
        name, _, mkt = k.partition("@")
        out.append({"kind": "plugin", "name": name, "marketplace": mkt})
    return out


def enabled_plugins(settings_path):
    return plugin_items(enabled_plugin_keys(settings_path))


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


def ollama_models(url="http://127.0.0.1:11434", timeout=2):
    """Models the running Ollama server has, via GET <url>/api/tags.

    Never shells out to `ollama list`: on Windows that auto-launches the Ollama tray app
    and server when none is running, and both outlive this run. A server that is down
    just means no model items (with a warning)."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        models = data.get("models", []) if isinstance(data, dict) else []
        return [{"kind": "model", "name": m["name"], "engine": "ollama-local"}
                for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)]
    except (OSError, ValueError) as e:
        print(f"WARNING: no Ollama server answered at {url} ({e}); skipping model enumeration",
              file=sys.stderr)
        return []


def main():
    scan = cfg().get("scan", {})
    items = []
    gate = registry_gate(scan["marketplaces_registry"]) if scan.get("marketplaces_registry") else None
    roots = scan.get("skill_roots", [])
    keep = gate
    enabled = enabled_plugin_keys(scan["claude_settings"]) if scan.get("claude_settings") else None
    if scan.get("installed_plugins"):
        # Plugin skills come from each enabled plugin's live install dir. Walking the
        # plugins tree as a plain skill root (old configs did) would add every stale
        # cached version and every skill of plugins that are not installed.
        plugins_dir = _norm(os.path.dirname(os.path.expanduser(scan["installed_plugins"])))
        kept_roots = []
        for r in roots:
            if _under(_norm(r), plugins_dir):
                print(f"WARNING: skipping skill root {r}: plugin skills now come from "
                      f"scan.installed_plugins", file=sys.stderr)
            else:
                kept_roots.append(r)
        roots = kept_roots
        keep = lambda p: not _under(_norm(p), plugins_dir) and (gate is None or gate(p))  # noqa: E731
    items += find_skills(roots, keep)
    if scan.get("installed_plugins"):
        items += plugin_skills(plugin_installs(scan["installed_plugins"]), enabled)
    if scan.get("claude_settings"):
        items += plugin_items(enabled)
    if scan.get("agents_dir"):
        items += agents(scan["agents_dir"])
    if scan.get("mcp_dir"):
        items += local_mcp(scan["mcp_dir"])
    if scan.get("ollama_models"):
        items += ollama_models(cfg().get("embed", {}).get("url", "http://127.0.0.1:11434"))

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
