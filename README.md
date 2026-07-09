# Quartermaster

**Your agent studies every tool you have, so you don't have to remember them.**

If you use Claude Code (or any agent runtime) long enough, you accumulate hundreds of
skills, plugins, agents, and local models — and forget most of them. You stop reaching
for tools you already own. Quartermaster fixes the *knowing* problem:

1. **Enumerate** everything installed (skills, plugins, agents, Ollama models).
2. **Study** each one once with an agent fleet into a deep catalog entry — what it is,
   *when to use it*, *when NOT to*, what it pairs with (schema: `docs/entry-schema.md`).
3. **Query** it in plain words: *"what do I have for reviewing PRs?"* — semantic top-k
   over local embeddings, with an `/arsenal` skill template so your agent answers in chat.
4. **Self-maintain**: a weekly run diffs reality against the catalog, prunes uninstalled
   tools, stubs new ones, and queues them for study — at zero LLM cost.

Deliberately boring tech: plain Python + JSON files + a local Ollama embedding model.
No daemon, no database, no cloud.

## Requirements

- Python 3.10+ with `numpy`
- [Ollama](https://ollama.com) serving an embedding model (default `qwen3-embedding:0.6b`)
  — optional: without it, semantic search degrades to reading the catalog directly
- Windows-first: developed and tested on Windows; paths in the default config assume
  `~/.claude`. Nothing is Windows-*specific* except the scheduling example below —
  Linux/macOS should work but is untested. Reports welcome.

## Quick start

```
git clone https://github.com/NAJEMWEHBE/quartermaster
cd quartermaster
# edit quartermaster.config.json - work_dir, scan roots, embed model
python enumerate_arsenal.py        # what do you actually have?
python regen_arsenal.py            # diff -> regen_study_todo.json (everything is NEW on first run)
```

Then have your agent study the todo list using `prompts/study-agent.md` (a few items per
agent, modest concurrency), and:

```
python assemble_catalog.py                       # merge entries -> arsenal.json + ARSENAL.md
python regen_arsenal.py --prune --rebuild-index  # finalize + build the semantic index
python query_arsenal.py "what do I have for writing tests?"
```

Install the `/arsenal` chat skill from `skill/SKILL.md` (fill in your paths) so your
agent answers arsenal questions natively.

## Keeping it fresh

Schedule `weekly.py`:

```
# Windows
schtasks /Create /TN "Quartermaster-Weekly" /SC WEEKLY /D SUN /ST 05:00 /TR "python <path>\weekly.py"
# cron
0 5 * * 0 python /path/to/weekly.py
```

Each run is free (no LLM calls): new tools get stub entries immediately (visible to
queries, marked as stubs), uninstalled tools are pruned, and the log ends with
`pending study: N` — that's your cue to point an agent at the study queue.

## Calibrating the match threshold

Similarity scales differ per embedding model. Run
`python query_arsenal.py --sims "some junk phrase"` vs a few real queries; set
`query.min_sim` in the config just above the junk ceiling (0.60 fits
qwen3-embedding:0.6b).

## License

MIT
