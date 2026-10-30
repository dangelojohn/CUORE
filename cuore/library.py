"""CLI for the knowledge library.

    python -m cuore.library register <file> --source techauthority --title ... --doc-no ... --url ...
    python -m cuore.library index
"""
from __future__ import annotations

import argparse
import json
import sys

from . import bootstrap  # noqa: F401
from .services import library


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cuore.library")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("register", help="write the SOURCES record for a file already under <state>/library/<source>/<date>/")
    r.add_argument("file")
    r.add_argument("--source", required=True)
    r.add_argument("--title", required=True)
    r.add_argument("--doc-no", default="")
    r.add_argument("--url", default="")
    r.add_argument("--licence", default="")
    sub.add_parser("index", help="list all documents")
    a = ap.parse_args(argv)
    if a.cmd == "register":
        try:
            rec = library.register(a.file, a.source, a.title, a.doc_no, a.url, a.licence)
        except (OSError, ValueError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        print(json.dumps(rec, indent=2))
    else:
        docs = library.index()
        for d in docs:
            print(f"{d['retrieved']}  {d['source']:<14} {d['doc_no']:<14} {d['n_facts']:>4} facts  {d['title']}")
        print(f"{len(docs)} document(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
