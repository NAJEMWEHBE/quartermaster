# -*- coding: utf-8 -*-
"""The top-level scripts are entry points only: each calls one quartermaster.cli main,
and all policy (identity, entry shape, file names) lives in the package."""
import ast
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = {"enumerate_arsenal.py": "enumerate_main", "assemble_catalog.py": "assemble_main",
           "build_index.py": "build_index_main", "query_arsenal.py": "query_main",
           "regen_arsenal.py": "regen_main", "weekly.py": "weekly_main"}


@pytest.mark.parametrize("script,main", sorted(SCRIPTS.items()))
def test_each_script_only_hands_over_to_its_cli_main(script, main):
    with open(os.path.join(ROOT, script), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    body = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    assert [type(n).__name__ for n in body] == ["ImportFrom", "If"], f"{script} holds more than a hand-over"
    assert body[0].module == "quartermaster.cli" and [a.name for a in body[0].names] == [main]


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_each_script_runs_from_any_folder(script, tmp_path):
    """The skill and schedulers start the scripts from anywhere; --help needs no config."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, script), "--help"], cwd=str(tmp_path),
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "usage:" in r.stdout and script in r.stdout
