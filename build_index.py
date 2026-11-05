# -*- coding: utf-8 -*-
"""Build the semantic index over every catalog entry (needs numpy and Ollama).

Entry point only: the work happens in quartermaster/ (see quartermaster.cli.build_index_main).
Run with --help for the options.
"""
from quartermaster.cli import build_index_main

if __name__ == "__main__":
    raise SystemExit(build_index_main())
