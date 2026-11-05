# -*- coding: utf-8 -*-
"""Answer "what do I have for X?" from the catalog.

  python query_arsenal.py "reviewing a pull request"   # semantic top-k
  python query_arsenal.py --explain <tool-id>          # one tool's full entry

Exit codes: 0 ok | 1 usage | 2 EMBEDDING-UNAVAILABLE | 3 CATALOG-UNAVAILABLE | 4 INDEX-STALE.

Entry point only: the work happens in quartermaster/ (see quartermaster.cli.query_main).
Run with --help for the options.
"""
from quartermaster.cli import query_main

if __name__ == "__main__":
    raise SystemExit(query_main())
