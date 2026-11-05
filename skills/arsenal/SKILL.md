---
name: arsenal
description: Arsenal lookup in the owner's studied tool catalog. Use when they ask which of their installed skills, plugins, agents, MCP servers or models fits a need ("do I have something for X?"), or what one named tool does and when to use it.
---

# Arsenal

Answer from the owner's catalog, built by the Quartermaster engine bundled with this
plugin. Every tool you name comes from a command's output below.

## Need → tools

```
python "${CLAUDE_PLUGIN_ROOT}/query_arsenal.py" --k 5 "<the need in plain words>"
```

Present each hit in plain words: what it is, when to use it, its avoid_when, and how to
call it (the **Invoke** line for skills; the kind for plugins, agents and models). Then
say which one you would pick and why. For a vague need, query two or three phrasings and
merge the hits. Done when every tool you mention carries its invoke name or kind and you
have named your pick.

## One tool

```
python "${CLAUDE_PLUGIN_ROOT}/query_arsenal.py" --explain <tool-id>
```

An inexact id prints the candidates as `id (kind)`; rerun with the exact id. Explain in
plain words first, then the avoid_when, so the owner knows the boundaries.

## Exit codes

Each code has one meaning and one action:

| code | label | do this |
|---|---|---|
| 0 | | present the results |
| 1 | usage, or numpy missing (the message says which) | fix the call; `--explain` and reading `arsenal.json` need no numpy |
| 2 | EMBEDDING-UNAVAILABLE | answer from `arsenal.json` (path printed) and say semantic search was down; pass on any `ollama pull` hint |
| 3 | CATALOG-UNAVAILABLE | no catalog yet: relay the printed hint (config, or an older catalog it found), and point the owner at the README quick start |
| 4 | INDEX-STALE | answer from `arsenal.json` (path printed); tell the owner to run `regen_arsenal.py --rebuild-index` |

Answering from `arsenal.json`: match the need against each item's what, use_when and
triggers, and quote id, kind and avoid_when.

## Reading the answer

- The answer starts with the catalog's date. When it says the catalog is days old, or a
  tool the owner names is missing, suggest `python "${CLAUDE_PLUGIN_ROOT}/weekly.py"`.
- Entries marked `[STUB - not yet deep-studied]` are placeholders from the tool's own
  description: say the details are unverified.
- On Windows, `py -3` stands in for `python` when `python` is not on PATH.

The engine reads its config from `QUARTERMASTER_CONFIG`, else
`~/.quartermaster/quartermaster.config.json`, else the bundled defaults (data in
`~/.quartermaster`).
