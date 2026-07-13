# -*- coding: utf-8 -*-
import json
import sys

import assemble_catalog
import regen_arsenal


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_prune_recomputes_header(qm_env, monkeypatch):
    # 1. build the catalog from the fixture batches
    assemble_catalog.main()
    before = _load(qm_env / "arsenal.json")
    assert before["count"] == 7

    # 2. prune. The fixture scan config finds nothing live, so every non-model studied
    #    item is "removed" and pruned. What matters: the header is recomputed, not
    #    patched in place (the old bug left by_tier/by_kind/generated stale).
    monkeypatch.setattr(sys, "argv", ["regen_arsenal.py", "--prune"])
    assert regen_arsenal.main() == 0

    after = _load(qm_env / "arsenal.json")
    assert after["count"] < before["count"]          # something was pruned
    assert after["count"] == len(after["items"])     # count matches items
    assert after["count"] == sum(after["by_tier"].values())   # header consistent...
    assert after["count"] == sum(after["by_kind"].values())   # ...both breakdowns
    # a .bak of the pre-prune file was written, and ARSENAL.md regenerated fresh
    assert (qm_env / "arsenal.json.bak").exists()
    md = (qm_env / "ARSENAL.md").read_text(encoding="utf-8")
    assert md.startswith("# Your Arsenal")
