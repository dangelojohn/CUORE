"""Create/print the crawl-ingest token and set the allowed origins.

    .venv/Scripts/python.exe -X utf8 scripts/ingest_token.py --origins https://www.autodoc.co.uk
    ... --origins https://www.autodoc.co.uk https://store.mopar.com
    ... --rotate     (new token)      ... (no --origins) just prints current

Files live in CUORE_STATE_DIR (default: CUORE's usual state dir).
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--origins", nargs="*", help="allowed Origin values (replaces the list)")
    ap.add_argument("--rotate", action="store_true", help="generate a new token")
    a = ap.parse_args()
    from cuore.live.config import state_dir
    d = state_dir()
    tf, of = d / "ingest_token.txt", d / "ingest_origins.json"
    if a.origins is not None:
        bad = [o for o in a.origins
               if not o.startswith(("https://", "http://")) or o.rstrip("/") != o]
        if bad:
            sys.exit(f"origins must look like https://host (no trailing slash): {bad}")
        of.write_text(json.dumps(a.origins), encoding="utf-8")
    if a.rotate or not tf.exists():
        tf.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
    origins = json.loads(of.read_text(encoding="utf-8")) if of.exists() else []
    print(f"state dir : {d}")
    print(f"token     : {tf.read_text(encoding='utf-8').strip()}")
    print(f"origins   : {origins or 'NONE (all requests will be refused)'}")


if __name__ == "__main__":
    main()
