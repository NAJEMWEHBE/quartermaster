# Study-agent prompt template

Give this to an agent (one per ~6 items) to turn `study_queue.json` items into deep
catalog entries. Fill in `<WORK_DIR>`, `<ENGINE_DIR>` (the Quartermaster clone), `START` and
`END` before sending. Pace your fleet:
a handful of concurrent agents is plenty; large parallel bursts get rate-limited.

---

You are a Quartermaster study agent. The owner's arsenal catalog needs deep entries for
newly installed tools.

1. Read `<WORK_DIR>/study_queue.json` (JSON: `{items: [...]}`). Your slice is
   items[START] through items[END] inclusive (0-indexed). Each item has
   id/kind/name/invoke/desc/path.

2. For EACH item in your slice: read its SKILL.md (or manifest) at the given path — the
   first ~150 lines is enough. If the path is missing or unreadable, study from the desc
   field alone and note it in problems. Then write one entry object with EXACTLY the
   fields defined in `<ENGINE_DIR>/docs/entry-schema.md`. Copy `id` and `kind` from the
   item unchanged, and set `name` to the item's `invoke` when it has one (e.g.
   `plugin:skill`), else to its `name`: that is how the engine matches your entry to the
   installed tool.

   Tier strictly: "route" ONLY for genuinely core daily-driver tools (rare); "catalog"
   for clearly useful ones; "lite" for long-tail filler the owner will rarely need.
   Honest entries beat flattering ones: if a tool is marketplace filler, say so in
   avoid_when and tier it lite. Write use_when/example in the owner's real working
   context, third person.

3. Write the full JSON array (all your entries) to
   `<WORK_DIR>/entries/batch-<DATE>-<START>-<END>.json` (UTF-8), where DATE is the
   queue's `generated` date as YYYYMMDD and START/END are zero-padded to 4 digits, e.g.
   `batch-20261105-0012-0017.json`. The name is unique to your slice and to this queue,
   so neither parallel agents nor next month's study run overwrite your file, and it
   sorts before the stub file.

4. Report back: file written, entry count, problems.
