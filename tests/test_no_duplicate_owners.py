# -*- coding: utf-8 -*-
"""The scripts must be import-only for the owned policies: no local slug/nkey/normalize/
make_stub/embed_text/contains/FIELDS. Owners are matching.py / entry.py / catalog_file.py.
"""
import os
import re

import assemble_catalog
import build_index
import entry
import enumerate_arsenal
import matching
import query_arsenal
import regen_arsenal
import weekly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = ["assemble_catalog.py", "weekly.py", "regen_arsenal.py", "build_index.py",
           "query_arsenal.py", "enumerate_arsenal.py"]
FORBIDDEN = [r"def slug\b", r"def nkey\b", r"def normalize\b", r"def make_stub\b",
             r"def embed_text\b", r"def contains\b", r"FIELDS ="]


def test_no_local_policy_definitions_in_scripts():
    for s in SCRIPTS:
        with open(os.path.join(ROOT, s), encoding="utf-8") as f:
            src = f.read()
        for pat in FORBIDDEN:
            assert not re.search(pat, src), f"{s} still defines/declares {pat!r}"


def test_scripts_import_owners_not_redefine():
    # names that should be entirely gone from the script's namespace
    for absent in ("normalize", "FIELDS", "write_md", "make_stub", "slug", "nkey", "embed_text"):
        assert not hasattr(assemble_catalog, absent), f"assemble_catalog has {absent}"
    for absent in ("make_stub", "slug", "FIELDS", "normalize", "embed_text"):
        assert not hasattr(weekly, absent), f"weekly has {absent}"
    for absent in ("FIELDS", "normalize", "make_stub", "embed_text"):
        assert not hasattr(regen_arsenal, absent), f"regen has {absent}"

    # names that are legitimately imported must BE the owner's object (not a redefinition)
    assert weekly.nkey is matching.nkey
    assert regen_arsenal.nkey is matching.nkey
    assert regen_arsenal.contains is matching.contains
    assert build_index.embed_text is entry.embed_text
    assert query_arsenal.offline_label is entry.offline_label
    assert assemble_catalog.dedup_key is matching.dedup_key
