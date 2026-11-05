# -*- coding: utf-8 -*-
"""Scan installed skills, plugins, agents, MCP servers and models into
<work_dir>/arsenal_items.json. Read-only on ~/.claude.

Entry point only: the work happens in quartermaster/ (see quartermaster.cli.enumerate_main).
Run with --help for the options.
"""
from quartermaster.cli import enumerate_main

if __name__ == "__main__":
    raise SystemExit(enumerate_main())
