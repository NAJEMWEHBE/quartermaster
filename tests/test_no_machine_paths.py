# -*- coding: utf-8 -*-
"""The repo is public: no absolute paths or folder names from a developer's machine."""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# A Windows drive-letter path, or a temp marketplace clone id copied from a real machine.
MACHINE_PATH = re.compile(r"\b[A-Za-z]:\\{1,2}[A-Za-z]|temp_\d{6,}")


def test_no_machine_specific_paths_in_tracked_text_files():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    hits = []
    for rel in files:
        if not rel.endswith((".py", ".md", ".json", ".yml", ".txt")):
            continue
        with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if MACHINE_PATH.search(line):
                    hits.append(f"{rel}:{n}: {line.strip()[:80]}")
    assert hits == []
