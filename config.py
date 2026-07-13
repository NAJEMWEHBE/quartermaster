# -*- coding: utf-8 -*-
"""Shared config + embedding helpers for Quartermaster.

All scripts read quartermaster.config.json from this directory (or the path in
the QUARTERMASTER_CONFIG environment variable). See README for the schema.
"""
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get("QUARTERMASTER_CONFIG", os.path.join(HERE, "quartermaster.config.json"))

_cfg = None


def cfg():
    global _cfg
    if _cfg is None:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            _cfg = json.load(f)
        _cfg["work_dir"] = os.path.abspath(os.path.expanduser(_cfg["work_dir"]))
    return _cfg


def work_path(*parts):
    return os.path.join(cfg()["work_dir"], *parts)


def entries_dir():
    return work_path("entries")


def embed(texts, timeout=120):
    """Embed texts via the configured Ollama endpoint. Returns list of L2-normalized
    vectors. Raises on failure - callers decide whether to degrade."""
    e = cfg().get("embed", {})
    url = e.get("url", "http://127.0.0.1:11434").rstrip("/") + "/api/embed"
    model = e.get("model", "qwen3-embedding:0.6b")
    body = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    vecs = data.get("embeddings")
    if not vecs or len(vecs) != len(texts):
        raise RuntimeError(f"embed returned {0 if not vecs else len(vecs)} vectors for {len(texts)} inputs")
    out = []
    for v in vecs:
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        out.append([x / norm for x in v])
    return out


def log(msg):
    line = msg if isinstance(msg, str) else str(msg)
    print(line)
    lp = cfg().get("log_file")
    if lp:
        import datetime
        with open(os.path.join(cfg()["work_dir"], lp), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}  {line}\n")


if __name__ == "__main__":
    c = cfg()
    print(f"config OK: work_dir={c['work_dir']}")
    print(f"embed: {c.get('embed')}")
    print(f"scan roots: {c.get('scan', {}).get('skill_roots')}")
    sys.exit(0)
