# -*- coding: utf-8 -*-
"""Mass-prune circuit breaker (2026-07-19 incident): a transient enumeration collapse
(harness swept plugin cache dirs) made LIVE drop 368->252 and --prune silently dropped
129 studied items (35% of the catalog) in one pass. The guard refuses a prune that
would remove >= PRUNE_GUARD_MIN items AND > PRUNE_GUARD_FRAC of the studied catalog,
unless --force-prune is passed. Small prunes (< min-abs) are never refused, so the
7-item fixture in test_regen_prune keeps pruning freely."""
import json

from quartermaster import cli
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
    cli.assemble_main([])
    return _load(qm_env / "arsenal.json")


def test_mass_prune_refused(qm_env, capsys):
    before = _catalog_with_many(qm_env)
    assert before["count"] == 19  # 7 fixture + 12 bulk

    assert cli.regen_main(["--prune"]) == 0

    out = capsys.readouterr().out
    assert "PRUNE REFUSED" in out
    after = _load(qm_env / "arsenal.json")
    assert after["count"] == before["count"]           # catalog untouched
    assert not (qm_env / "arsenal.json.bak").exists()  # no prune, no .bak


def test_force_prune_overrides_guard(qm_env, capsys):
    before = _catalog_with_many(qm_env)

    assert cli.regen_main(["--prune", "--force-prune"]) == 0

    out = capsys.readouterr().out
    assert "PRUNE REFUSED" not in out
    assert "PRUNED" in out
    after = _load(qm_env / "arsenal.json")
    assert after["count"] < before["count"]
    assert (qm_env / "arsenal.json.bak").exists()


def test_a_forced_prune_is_not_refused_again_next_week(qm_env, capsys):
    """assemble rebuilds arsenal.json from every batch file each week, so the removals
    --force-prune accepted come back; the guard must not refuse them a second time."""
    _catalog_with_many(qm_env)
    assert cli.regen_main(["--prune", "--force-prune"]) == 0
    cli.assemble_main([])                      # the weekly run's assemble step
    capsys.readouterr()

    assert cli.regen_main(["--prune"]) == 0
    out = capsys.readouterr().out
    assert "PRUNE REFUSED" not in out and "PRUNED" in out

    # a fresh collapse on top of the accepted removals is still refused
    write_json(qm_env / "entries" / "batch-04-more.json", [
        {"id": f"more{i}", "kind": "skill", "name": f"More{i}", "what": "w",
         "use_when": "u", "avoid_when": "a", "tier": "catalog"} for i in range(12)])
    cli.assemble_main([])
    capsys.readouterr()
    assert cli.regen_main(["--prune"]) == 0
    assert "PRUNE REFUSED: 12/" in capsys.readouterr().out
