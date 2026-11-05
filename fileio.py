# -*- coding: utf-8 -*-
"""Owner of how the engine writes its files: atomically.

Every file in the work dir is written to a temp file beside it and then moved over the
old one (os.replace), so a reader running at the same time (a query during the weekly
job) or a crash mid-write never sees a half-written file: it sees the old one or the new
one. Readers stay plain json.load.
"""
import json
import os
import tempfile
import time


def _replace(src, dst, tries=10):
    # Windows refuses the swap while another process holds dst open; readers only keep
    # it open for a moment, so retry briefly before giving up.
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def write_with(path, write, mode="w", encoding="utf-8"):
    """Call write(f) on a temp file beside `path`, then move it into place. On any
    error the temp file is removed and `path` is left as it was."""
    path = os.fspath(path)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        kw = {} if "b" in mode else {"encoding": encoding, "newline": ""}
        with os.fdopen(fd, mode, **kw) as f:
            write(f)
        _replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def write_text(path, text):
    write_with(path, lambda f: f.write(text))


def write_json(path, obj, indent=2):
    write_with(path, lambda f: json.dump(obj, f, indent=indent, ensure_ascii=False))


def read_json(path):
    """json.load with the file closed again right away (Windows can't replace an open file)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)
