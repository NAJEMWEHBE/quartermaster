---
name: arsenal
description: Answer "what do I have for X?" from the owner's studied tool catalog (skills/plugins/agents/models with use_when/avoid_when). Use when they ask what tool/skill/plugin they have for a need, whether something exists in their arsenal, "do I have something for...", "which of my tools...", or want a specific tool explained ("what does X do?", "when do I use X?").
---

# Arsenal — the Quartermaster knowing layer

The owner forgets what tools they own. This skill answers from the studied catalog —
never from memory.

> Template note: replace `<PYTHON>` and `<QM_DIR>` with your install's paths, or ship a
> wrapper script on PATH.

## Need → tools ("what do I have for X?")

```
<PYTHON> <QM_DIR>/query_arsenal.py --k 5 "<the need in plain words>"
```

Semantic top-k over the catalog. Present the hits in plain words: what each tool is,
when to use it, how to invoke it. If several fit, say which YOU would pick and why.
If the query is vague, query with 2-3 phrasings and merge.

## Single tool ("what does X do?")

```
<PYTHON> <QM_DIR>/query_arsenal.py --explain <tool-id>
```

Forgiving lookup (substring match, lists candidates when ambiguous). Explain simply —
plain words first, then the avoid_when so the owner knows the boundaries.

## Degrade path (exit code 2 = embedding down)

If the script reports EMBEDDING-UNAVAILABLE, do NOT give up: read `arsenal.json` in the
work dir directly (fields: id/what/use_when/avoid_when/triggers/tier) and answer from
that. Say semantic search was down.

## Known limits (be honest about them)

- The semantic index covers **skills only**; plugins/agents/models are in arsenal.json
  but not embedded — for "what agents do I have?" read the catalog directly.
- Catalog freshness = last regen. If a tool the owner mentions is missing, note it and
  suggest running `weekly.py`.
- Entries marked `[STUB - not yet deep-studied]` are unverified placeholders — say so.
