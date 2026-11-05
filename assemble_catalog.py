# -*- coding: utf-8 -*-
"""Merge <work_dir>/entries/batch-*.json into arsenal.json, ARSENAL.md and
quality-report.txt.

Entry point only: the work happens in quartermaster/ (see quartermaster.cli.assemble_main).
Run with --help for the options.
"""
from quartermaster.cli import assemble_main

if __name__ == "__main__":
    raise SystemExit(assemble_main())
