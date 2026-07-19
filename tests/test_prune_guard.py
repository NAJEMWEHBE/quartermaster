# -*- coding: utf-8 -*-
"""Mass-prune circuit breaker (2026-07-19 incident): a transient enumeration collapse
(harness swept plugin cache dirs) made LIVE drop 368->252 and --prune silently dropped
129 studied items (35% of the catalog) in one pass. The guard refuses a prune that
would remove >= PRUNE_GUARD_MIN items AND > PRUNE_GUARD_FRAC of the studied catalog,
unless --force-prune is passed. Small prunes (< min-abs) are never refused, so the
7-item fixture in test_regen_prune keeps pruning freely."""
import json
import sys

import assemble_catalog
import regen_arsenal
from conftest import write_json

# 12 extra studied skills so prunable (18 non-model) clears PRUNE_GUARD_MIN and the
# fixture's empty scan config makes ALL of them "removed" — the collapse scenario.
BATCH_MANY = [
    {"id": f"bulk{i}", "kind": "skill", "name": f"Bulk{i}", "what": "bulk item",
     "use_when": "u", "avoid_when": "a", "tier": "catalog"}
    for i in range(12)
]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _catalog_with_many(qm_env):
    write_json(qm_env / "entries" / "batch-03-many.json", BATCH_MANY)
    assemble_catalog.main()
    return _load(qm_env / "arsenal.json")


def test_mass_prune_refused(qm_env, monkeypatch, capsys):
    before = _catalog_with_many(qm_env)
    assert before["count"] == 19  # 7 fixture + 12 bulk

    monkeypatch.setattr(sys, "argv", ["regen_arsenal.py", "--prune"])
    assert regen_arsenal.main() == 0

    out = capsys.readouterr().out
    assert "PRUNE REFUSED" in out
    after = _load(qm_env / "arsenal.json")
    assert after["count"] == before["count"]           # catalog untouched
    assert not (qm_env / "arsenal.json.bak").exists()  # no prune, no .bak


def test_force_prune_overrides_guard(qm_env, monkeypatch, capsys):
    before = _catalog_with_many(qm_env)

    monkeypatch.setattr(sys, "argv", ["regen_arsenal.py", "--prune", "--force-prune"])
    assert regen_arsenal.main() == 0

    out = capsys.readouterr().out
    assert "PRUNE REFUSED" not in out
    assert "PRUNED" in out
    after = _load(qm_env / "arsenal.json")
    assert after["count"] < before["count"]
    assert (qm_env / "arsenal.json.bak").exists()
