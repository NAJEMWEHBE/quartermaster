# Quartermaster

**Your agent studies every tool you have, so you don't have to remember them.**

If you use Claude Code (or any agent runtime) long enough, you accumulate hundreds of
skills, plugins, agents, and local models — and forget most of them. You stop reaching
for tools you already own. Quartermaster fixes the *knowing* problem:

1. **Enumerate** every tool you have enabled: the skills Claude Code actually loads
   (your own and those of enabled plugins), plugins, agents, local MCP servers and
   Ollama models.
2. **Study** each one once with an agent fleet into a deep catalog entry — what it is,
   *when to use it*, *when NOT to*, what it pairs with (schema: `docs/entry-schema.md`).
3. **Query** it in plain words: *"what do I have for reviewing PRs?"* — semantic top-k
   over local embeddings, through the `arsenal` skill so your agent answers in chat.
4. **Self-maintain**: a weekly run diffs reality against the catalog, prunes uninstalled
   tools, stubs new ones, and queues them for study — at zero LLM cost.

Deliberately boring tech: plain Python + JSON files + a local Ollama embedding model.
No daemon, no database, no cloud.

## Requirements

- Python 3.10+ and `numpy` (`pip install -r requirements.txt`)
- [Ollama](https://ollama.com) serving an embedding model: `ollama pull qwen3-embedding:0.6b`.
  Optional: without it, the skill answers from the catalog file directly. Quartermaster
  only talks to a running Ollama server; it never starts one.
- Windows-first: developed and tested on Windows, and CI also runs on Ubuntu. The default
  config reads `~/.claude`.

## Quick start

```
git clone https://github.com/NAJEMWEHBE/quartermaster
cd quartermaster
pip install -r requirements.txt
ollama pull qwen3-embedding:0.6b
python enumerate_arsenal.py        # what do you actually have?
python regen_arsenal.py            # diff -> study_queue.json (everything is unstudied on first run)
```

Then have your agent study `~/.quartermaster/study_queue.json` with
`prompts/study-agent.md` (a few items per agent, modest concurrency), and:

```
python assemble_catalog.py                       # merge entries -> arsenal.json + ARSENAL.md
python regen_arsenal.py --prune --rebuild-index  # finalize + build the semantic index
python query_arsenal.py "what do I have for writing tests?"
```

Every script takes `--help`.

## Where things live

- **Data**: `~/.quartermaster/` (catalog, index, study queue, `entries/`, `weekly.log`).
- **Config**, first one found:
  1. the file named by the `QUARTERMASTER_CONFIG` environment variable
  2. `~/.quartermaster/quartermaster.config.json`
  3. `quartermaster.config.json` shipped with the engine

  To change scan roots, the embed model or the data folder, copy the shipped config to
  `~/.quartermaster/` and edit that copy; plugin updates then leave it alone. Relative
  paths in a config resolve beside that config file, never against the current folder.

**Upgrading from 1.0**: the old default kept data in `<clone>/data`. Move that folder's
contents to `~/.quartermaster/`, or set `work_dir` to it in your config; the query
points at an old catalog it finds there. The first prune after upgrading may also be
refused as a mass prune, because 1.1 stops counting skills of disabled or not-installed
plugins. Check the removed list in `regen_plan.json`, then run
`python regen_arsenal.py --prune --force-prune` once; weekly runs prune normally after that.

## The arsenal chat skill

This repo is also a Claude Code **plugin marketplace**, and the plugin bundles the
engine. In the app: Settings → Plugins → Add marketplace → enter
`NAJEMWEHBE/quartermaster` → Sync → enable the **quartermaster** plugin.

CLI equivalent: `/plugin marketplace add NAJEMWEHBE/quartermaster` then
`/plugin install quartermaster@quartermaster`.

Then ask *"do I have something for X?"*, or call the skill as `/quartermaster:arsenal`.
The skill runs the bundled `query_arsenal.py` and reads the same `~/.quartermaster`
data as your clone.

## Keeping it fresh

Schedule `weekly.py`. Use absolute paths: schedulers start in their own folder.

```
# Windows (Task Scheduler)
#   (from cmd; use the full path of your python.exe and of your clone)
schtasks /Create /TN "Quartermaster-Weekly" /SC WEEKLY /D SUN /ST 05:00 /TR "\"%LOCALAPPDATA%\Programs\Python\Python313\python.exe\" \"%USERPROFILE%\quartermaster\weekly.py\""
# cron
0 5 * * 0 /usr/bin/python3 /path/to/quartermaster/weekly.py
```

Each run is free (no LLM calls): new tools get stub entries immediately (visible to
queries, marked as stubs), uninstalled tools are pruned, and the log ends with
`pending study N`: your cue to point an agent at `~/.quartermaster/study_queue.json`.

## Exit codes

| script | code | meaning |
|---|---|---|
| `query_arsenal.py` | 0 | ok |
| | 1 | usage error, or numpy missing |
| | 2 | EMBEDDING-UNAVAILABLE: no embedding server answered, or the model isn't pulled; `arsenal.json` is fine |
| | 3 | CATALOG-UNAVAILABLE: no readable `arsenal.json` in the work dir |
| | 4 | INDEX-STALE: index missing, built with another model, or left half-written by a failed build; run `regen_arsenal.py --rebuild-index` |
| `regen_arsenal.py`, `weekly.py` | 0 | ok |
| | 1 | a step failed (the scan, or assemble); nothing half-written |
| | 4 | the catalog is up to date but the index build failed (weekly logs `INDEX STALE`) |

## Calibrating search

Similarity scales differ per embedding model. Run
`python query_arsenal.py --sims "some junk phrase"` vs a few real queries; set
`query.min_sim` in the config just above the junk ceiling (0.60 fits
qwen3-embedding:0.6b).

Instruction-tuned embedders (qwen3-embedding is one) can rank better when the query
carries a task line. Set `"embed": {"query_instruction": "Find the installed tool that
fits this need"}` to send queries as `Instruct: <that>\nQuery: <your words>`. It is off
by default; compare `--sims` output with and without it before keeping it.

## Code layout

```
quartermaster/        the engine package
  config.py           where the config is found; paths resolved beside it
  inventory.py        the live scan (which skills Claude Code loads, plugins, agents, models)
  matching.py         tool identity: is this catalog entry still an installed tool?
  entry.py            the catalog entry record, stubs, the ARSENAL.md renderer
  catalog_file.py     the arsenal.json contract
  workspace.py        every file name in the work dir, atomic writes
  embedder.py         the embedder seam (Ollama adapter)
  index.py            build and search the semantic index
  pipeline.py         enumerate / assemble / regen / weekly, each returning a result object
  cli.py              argument parsing and output for each script
*.py                  entry points: each calls one cli function
skills/arsenal/       the chat skill
prompts/              the study-agent prompt
docs/entry-schema.md  the entry fields and their owners
```

## Tests

```
pip install -r requirements.txt pytest
python -m pytest
```

No network: embeddings are faked through the embedder seam, and scans run against
temporary folders. CI runs Ubuntu and Windows on Python 3.10 and 3.13.

## License

MIT
