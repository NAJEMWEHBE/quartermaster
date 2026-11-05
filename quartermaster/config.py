# -*- coding: utf-8 -*-
"""Owner of the engine config: where it is found and what its paths mean.

Lookup order (read on every call, so a changed environment is seen at once):
  1. the QUARTERMASTER_CONFIG environment variable
  2. ~/.quartermaster/quartermaster.config.json, if it exists
  3. quartermaster.config.json shipped beside the scripts (data in ~/.quartermaster)

Every relative path in a config resolves beside that config file, never against the
current folder: the /arsenal skill and schedulers run the scripts from anywhere.
"""
import json
import os

ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(ENGINE_DIR, "quartermaster.config.json")
HOME = os.path.join("~", ".quartermaster")

# Config keys that hold a filesystem path (scan.skill_roots holds a list of them).
SCAN_PATH_KEYS = ("installed_plugins", "marketplaces_registry", "agents_dir",
                  "claude_settings", "mcp_dir")

_cache = {}


def config_path():
    """The config file in use, by the lookup order above."""
    env = os.environ.get("QUARTERMASTER_CONFIG")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    user = os.path.expanduser(os.path.join(HOME, "quartermaster.config.json"))
    return user if os.path.isfile(user) else DEFAULT_CONFIG


def resolve_path(p, base):
    """~ expanded; a relative path is relative to `base` (the config file's folder)."""
    if not isinstance(p, str) or not p:
        return p
    return os.path.normpath(os.path.join(base, os.path.expanduser(p)))


def load(path):
    """Read one config file and resolve its paths. Always a fresh dict."""
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    c["work_dir"] = resolve_path(c.get("work_dir") or HOME, base)
    c["copy_to"] = resolve_path(c.get("copy_to"), base)
    scan = c.setdefault("scan", {})
    for k in SCAN_PATH_KEYS:
        if k in scan:
            scan[k] = resolve_path(scan[k], base)
    if isinstance(scan.get("skill_roots"), list):
        scan["skill_roots"] = [resolve_path(r, base) for r in scan["skill_roots"]]
    c.setdefault("embed", {})
    c.setdefault("query", {})
    return c


def cfg(path=None):
    """The config dict for `path` (default: config_path()). Cached until the file (or
    the home folder that ~ means) changes, so callers in one run share one dict."""
    path = os.path.abspath(path or config_path())
    stamp = (os.stat(path).st_mtime_ns, os.path.expanduser("~"))
    hit = _cache.get(path)
    if hit is None or hit[0] != stamp:
        hit = _cache[path] = (stamp, load(path))
    return hit[1]
