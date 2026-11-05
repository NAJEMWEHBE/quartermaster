# -*- coding: utf-8 -*-
"""The recurring zero-LLM self-maintenance run; schedule it weekly (see README).

Entry point only: the work happens in quartermaster/ (see quartermaster.cli.weekly_main).
Run with --help for the options.
"""
from quartermaster.cli import weekly_main

if __name__ == "__main__":
    raise SystemExit(weekly_main())
