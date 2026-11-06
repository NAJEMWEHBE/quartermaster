# -*- coding: utf-8 -*-
"""Owner of the work dir: the name of every file in it, and how they are written.

Every write is atomic: the bytes go to a temp file beside the target, which is then
moved over the old one (os.replace). A reader running at the same time (a query during
the weekly job) or a crash mid-write sees the old file or the new one, never half a file;
the data is fsynced before the move, so a power cut can't leave an empty file either.
"""
import datetime
import json
import os
import re
import tempfile
import time

CATALOG = "arsenal.json"
CATALOG_MD = "ARSENAL.md"
QUALITY = "quality-report.txt"
ITEMS = "arsenal_items.json"          # the live inventory from the last scan
PLAN = "regen_plan.json"
STUDY_QUEUE = "study_queue.json"
LEGACY_TODO = "regen_study_todo.json"  # the old, NEW-only queue; removed when seen
PRUNED_LAST = "pruned_last.json"       # what the last prune removed (see pipeline.regen)
INDEX_VECTORS = "arsenal_index.npz"
INDEX_META = "arsenal_index.meta.json"
ENTRIES = "entries"
STUBS = os.path.join(ENTRIES, "batch-zz-stubs.json")  # 'zz' sorts last: deep entries win

# C0 controls except tab and newline, DEL, and the C1 controls. Text from installed tools,
# study agents and the embedding server reaches the console and the log; a terminal acts
# on these characters, so they are shown as visible \xNN escapes instead.
_CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def term_safe(text):
    """`text` with every terminal control character except tab and newline made visible.

    Windows line endings (CRLF) become plain newlines first, so they don't show as escapes."""
    return _CONTROLS.sub(lambda m: "\\x%02x" % ord(m.group()), str(text).replace("\r\n", "\n"))


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


def _umask():
    mask = os.umask(0)
    os.umask(mask)
    return mask


def write_with(path, write, mode="w", encoding="utf-8"):
    """Call write(f) on a temp file beside `path`, then move it into place. On any
    error the temp file is removed and `path` is left as it was."""
    path = os.fspath(path)
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=folder)
    try:
        if os.name == "posix":  # mkstemp makes the file owner-only; give it the usual mode
            os.chmod(tmp, 0o666 & ~_umask())
        kw = {} if "b" in mode else {"encoding": encoding, "newline": ""}
        with os.fdopen(fd, mode, **kw) as f:
            write(f)
            f.flush()
            os.fsync(f.fileno())  # data on disk before the rename, or a power cut can empty it
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


class Workspace:
    """One work dir. `ws.path(name)` for any file in it; the name constants above are
    the only file names the engine uses."""

    def __init__(self, work_dir, log_file=None):
        self.dir = os.path.abspath(os.path.expanduser(work_dir))
        self.log_file = log_file

    @classmethod
    def from_config(cls, c):
        return cls(c["work_dir"], c.get("log_file"))

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    def read_json(self, name):
        return read_json(self.path(name))

    def write_json(self, name, obj, indent=2):
        write_json(self.path(name), obj, indent)

    def write_text(self, name, text):
        write_text(self.path(name), text)

    def remove(self, name):
        try:
            os.remove(self.path(name))
        except FileNotFoundError:
            pass

    def exists(self, name):
        return os.path.exists(self.path(name))

    def log(self, line):
        """Print a line and, when the config names a log file, append it with a timestamp.
        Control characters are made visible and newlines escaped: one call, one log line."""
        line = term_safe(line).replace("\n", "\\n")
        print(line)
        if self.log_file:
            os.makedirs(self.dir, exist_ok=True)
            stamp = datetime.datetime.now().isoformat(timespec="seconds")
            with open(self.path(self.log_file), "a", encoding="utf-8") as f:
                f.write(f"{stamp}  {line}\n")
