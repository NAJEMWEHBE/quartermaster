# Catalog entry schema

Every tool in `arsenal.json` is one entry with these fields. Study agents (see
`prompts/study-agent.md`) produce them; `assemble_catalog.py` normalizes and merges them.

| field | type | meaning |
|---|---|---|
| `id` | string | kebab-case unique id, usually the tool name |
| `kind` | string | `skill` \| `plugin` \| `agent` \| `mcp` \| `model` |
| `name` | string | display name as installed |
| `what` | string | 1-2 plain-words sentences: what the tool actually is/does |
| `use_when` | string | when to reach for it — concrete situations, not marketing |
| `avoid_when` | string | when NOT to use it, and what to use instead |
| `offline` | bool \| `"partial"` | works without network? |
| `cost` | string | e.g. `free-local`, `api-tokens`, `free` |
| `pairs_with` | string[] | ids of tools it combos with |
| `supersedes` | string[] | ids of tools it replaces (usually empty) |
| `triggers` | string[] | 3-5 short phrases someone would say when this tool fits |
| `example` | string | one concrete usage sentence in the owner's real context |
| `tier` | string | `route` (core daily driver — rare) \| `catalog` (clearly useful) \| `lite` (long-tail) |
| `route_patterns` | string[] | salience markers for `tier=route` items: 2-4 lowercase regex trigger patterns |

> **`tier=route` / `route_patterns` are salience markers only.** This engine has no
> router — nothing consumes `route_patterns` to auto-invoke a tool. They simply flag
> the handful of daily-driver tools (surfaced first in `ARSENAL.md`, checked for
> quality by `assemble_catalog.py`). The fields are kept so a downstream router *could*
> use them, but the OSS engine never does.

Honesty rule: entries that call marketplace filler what it is (`tier: lite`, blunt
`avoid_when`) make the whole catalog trustworthy. Flattering entries poison retrieval.

## Owning modules

The entry record and its policies each have a single owner; scripts import them and
never re-derive them:

- **`entry.py`** — the `Entry` record: `FIELDS` (the 14-field contract + order), the
  `Tier` vocabulary, `offline_label` (the `offline`/`partial`/`online` tri-state),
  `Entry.from_raw` (normalization), `Entry.make_stub` (stub records), `md_block` /
  `render_md` (the one `ARSENAL.md` renderer), and `embed_text` (the semantic-index
  template).
- **`matching.py`** — the match policy: `slug`, `nkey` (parenthetical-stripping match
  key), `contains` (fuzzy model-tag containment), `dedup_key`.
- **`catalog_file.py`** — the `arsenal.json` contract: `build` / `write` / `parse`. The
  header (`count`/`by_tier`/`by_kind`/`generated`) is recomputed from the items on every
  write, so it can never drift out of sync with `items`.

## Stubs

`weekly.py` gives newly-installed tools a placeholder entry in
`entries/batch-zz-stubs.json` (marked `[STUB - not yet deep-studied]`, `tier: lite`)
so queries see them immediately. The stub file doubles as the deep-study queue; a stub
retires automatically once a real entry for the same id appears in any other batch file,
or the tool is uninstalled.
