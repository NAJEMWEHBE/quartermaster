# -*- coding: utf-8 -*-
"""Owner of the live inventory: what is installed right now (see scan()).

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
import glob
import json
import os
import sys
import urllib.error
import urllib.request

from .frontmatter import frontmatter


class InventoryError(Exception):
    """A configured inventory source exists but can't be read."""


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
    registered from anywhere on disk (say, one folder inside a projects folder), so
    parent-inference promoted whole project trees into gate zones: every skill in such
    a tree outside the one registered dir vanished from LIVE and became prune bait.

    Fails OPEN (predicate always True, warning on stderr) whenever the registry is unset,
    unreadable or malformed, so this only ever removes provable orphans.

    2026-07-19: widening the scan root to plugins/marketplaces swept in a leftover
    temp_* clone and its skills - this gate is the structural fix for that class."""
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
        raise InventoryError(f"cannot read {path} ({type(e).__name__}: {e})")
    plugins = reg.get("plugins", reg) if isinstance(reg, dict) else None
    if not isinstance(plugins, dict):
        raise InventoryError(f"{path} has no plugins object")
    out = {}
    for key, recs in plugins.items():
        recs = [r for r in (recs if isinstance(recs, list) else [recs])
                if isinstance(r, dict) and isinstance(r.get("installPath"), str)]
        recs.sort(key=lambda r: r.get("scope") != "user")  # user scope first
        live = next((r["installPath"] for r in recs if os.path.isdir(os.path.expanduser(r["installPath"]))), None)
        if live:
            out[key] = os.path.expanduser(live)
        else:
            print(f"WARNING: {key} is installed but its folder is missing; its skills are not "
                  f"listed until it is reinstalled", file=sys.stderr)
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


def _read_json_quiet(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _declared_skills(root, plugin):
    """The skill paths a plugin declares: its plugin.json `skills`, else the `skills` of
    its entry in a marketplace.json shipped in the same folder (whole-repo plugins with
    source "./"). None when nothing is declared."""
    meta = os.path.join(root, ".claude-plugin")
    pj = _read_json_quiet(os.path.join(meta, "plugin.json"))
    declared = pj.get("skills") if isinstance(pj, dict) else None
    if not declared:
        mj = _read_json_quiet(os.path.join(meta, "marketplace.json"))
        entries = mj.get("plugins") if isinstance(mj, dict) else None
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and e.get("name") == plugin and e.get("skills"):
                declared = e["skills"]
    if isinstance(declared, str):
        declared = [declared]
    return [d for d in declared if isinstance(d, str)] if isinstance(declared, list) else None


def plugin_skill_files(root, plugin):
    """The SKILL.md files Claude Code loads for one plugin: each declared path (a skill
    folder, or a folder of skill folders), or by default skills/<name>/SKILL.md. Drafts
    deeper in the tree and SKILL.md files elsewhere in the repo are not loaded."""
    declared = _declared_skills(root, plugin)
    if declared is None:
        return sorted(glob.glob(os.path.join(root, "skills", "*", "SKILL.md")))
    files = []
    for d in declared:
        d = os.path.normpath(os.path.join(root, d))
        own = os.path.join(d, "SKILL.md")
        files += [own] if os.path.isfile(own) else sorted(glob.glob(os.path.join(d, "*", "SKILL.md")))
    return files


def plugin_skills(installs, enabled=None):
    """Skills of each installed plugin that is enabled (all installed ones if `enabled`
    is None), read from the plugin's live install dir only."""
    out, seen = [], set()
    for key in sorted(installs):
        if enabled is not None and key not in enabled:
            continue
        plugin, _, mkt = key.partition("@")
        for p in plugin_skill_files(installs[key], plugin):
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


def _plugins_registry_above(root, levels=3):
    """installed_plugins.json in `root` or up to `levels` folders above it, else None."""
    d = os.path.abspath(os.path.expanduser(root))
    for _ in range(levels + 1):
        f = os.path.join(d, "installed_plugins.json")
        if os.path.isfile(f):
            return f
        d = os.path.dirname(d)
    return None


def scan(scan_cfg, ollama_url="http://127.0.0.1:11434"):
    """The live inventory: a list of item dicts (kind, name, and per kind invoke, desc,
    path, plugin, marketplace). Raises InventoryError when a source of truth that is
    configured can't be read, so a broken scan never looks like a mass uninstall."""
    items = []
    gate = registry_gate(scan_cfg["marketplaces_registry"]) if scan_cfg.get("marketplaces_registry") else None
    roots = scan_cfg.get("skill_roots") or []
    keep = gate
    enabled = enabled_plugin_keys(scan_cfg["claude_settings"]) if scan_cfg.get("claude_settings") else None
    if scan_cfg.get("installed_plugins"):
        # Plugin skills come from each enabled plugin's live install dir. Walking the
        # plugins tree as a plain skill root (old configs did) would add every stale
        # cached version and every skill of plugins that are not installed.
        plugins_dir = _norm(os.path.dirname(os.path.expanduser(scan_cfg["installed_plugins"])))
        kept_roots = []
        for r in roots:
            if _under(_norm(r), plugins_dir):
                print(f"WARNING: skipping skill root {r}: plugin skills now come from "
                      f"scan.installed_plugins", file=sys.stderr)
            else:
                kept_roots.append(r)
        roots = kept_roots

        def keep(p):
            return not _under(_norm(p), plugins_dir) and (gate is None or gate(p))
    else:
        for r in roots:
            reg = _plugins_registry_above(r)
            if reg:
                print(f"WARNING: skill root {r} is inside a Claude plugins folder, which lists "
                      f"stale versions and uninstalled plugins under bare names. Set "
                      f"scan.installed_plugins to {reg} and drop this root.", file=sys.stderr)
    items += find_skills(roots, keep)
    if scan_cfg.get("installed_plugins"):
        items += plugin_skills(plugin_installs(scan_cfg["installed_plugins"]), enabled)
    if scan_cfg.get("claude_settings"):
        items += plugin_items(enabled)
    if scan_cfg.get("agents_dir"):
        items += agents(scan_cfg["agents_dir"])
    if scan_cfg.get("mcp_dir"):
        items += local_mcp(scan_cfg["mcp_dir"])
    if scan_cfg.get("ollama_models"):
        items += ollama_models(ollama_url)
    return items
