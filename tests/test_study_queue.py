# -*- coding: utf-8 -*-
"""The study queue: every live tool that has no deep entry yet, with what a study
agent needs (source path and description), rebuilt on every regen run."""
import json
import sys

import assemble_catalog
import config
import regen_arsenal
from conftest import write_json
from entry import Entry


def _scan_skills(qm_env, tmp_path, *names):
    root = tmp_path / "skills"
    for n in names:
        (root / n).mkdir(parents=True)
        (root / n / "SKILL.md").write_text(f"---\nname: {n}\ndescription: what {n} does\n---\n",
                                           encoding="utf-8")
    with open(config.CONFIG_PATH, encoding="utf-8") as f:
        c = json.load(f)
    c["scan"]["skill_roots"] = [str(root)]
    with open(config.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(c, f)  # regen starts enumerate as a script, which reads this file
    config._cfg = None
    return root


def _regen(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["regen_arsenal.py"])
    assert regen_arsenal.main() == 0


def _queue(qm_env):
    p = qm_env / "study_queue.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def test_queue_lists_unstudied_tools_with_path_and_desc_until_a_deep_entry_lands(
        qm_env, tmp_path, monkeypatch, capsys):
    root = _scan_skills(qm_env, tmp_path, "foo", "fresh")
    assemble_catalog.main()            # the fixture catalog has a deep `foo`

    _regen(monkeypatch)
    q = _queue(qm_env)
    assert [(i["id"], i["name"], i["desc"]) for i in q["items"]] == [("fresh", "fresh", "what fresh does")]
    assert q["items"][0]["path"] == str(root / "fresh" / "SKILL.md")
    assert q["count"] == 1

    # weekly stubs `fresh`: a stub is not a study, so it stays queued, path and all
    write_json(qm_env / "entries" / "batch-zz-stubs.json",
               [Entry.make_stub(q["items"][0]).to_dict()])
    assemble_catalog.main()
    _regen(monkeypatch)
    assert [i["path"] for i in _queue(qm_env)["items"]] == [str(root / "fresh" / "SKILL.md")]

    # a deep entry lands: the queue is empty, so the file goes away
    write_json(qm_env / "entries" / "batch-03-fresh.json", [
        {"id": "fresh", "kind": "skill", "name": "fresh", "what": "w", "use_when": "u",
         "avoid_when": "a", "tier": "catalog"}])
    assemble_catalog.main()
    _regen(monkeypatch)
    assert _queue(qm_env) is None


def test_the_old_todo_file_is_removed_so_agents_cannot_read_a_stale_queue(qm_env, tmp_path, monkeypatch):
    _scan_skills(qm_env, tmp_path, "fresh")
    (qm_env / "regen_study_todo.json").write_text('{"items": []}', encoding="utf-8")
    _regen(monkeypatch)
    assert not (qm_env / "regen_study_todo.json").exists()
    assert _queue(qm_env)["count"] == 1
