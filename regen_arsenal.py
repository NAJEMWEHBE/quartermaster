# -*- coding: utf-8 -*-
"""Diff the live inventory against the studied catalog; optionally prune and
rebuild the index (--prune, --force-prune, --rebuild-index).

Entry point only: the work happens in quartermaster/ (see quartermaster.cli.regen_main).
Run with --help for the options.
"""
from quartermaster.cli import regen_main

if __name__ == "__main__":
    raise SystemExit(regen_main())
