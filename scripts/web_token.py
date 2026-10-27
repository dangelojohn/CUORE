"""Lock/unlock CUORE's web UI with a token kept in CUORE_STATE_DIR/web_token.txt.

    .venv/Scripts/python.exe -X utf8 scripts/web_token.py --set          (make one, or keep existing)
    ... --set MYTOKEN    use this exact token      ... --rotate   (new token; logs everyone out)
    ... --show           print current             ... --clear    (unlock: delete the file)

Restart is not needed: the file is read on each request. CUORE_TOKEN in the
environment, if set, takes precedence over the file.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", nargs="?", const="", metavar="TOKEN")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--clear", action="store_true")
    a = ap.parse_args()
    from cuore.live.config import state_dir
    f = state_dir() / "web_token.txt"
    if a.clear:
        f.unlink(missing_ok=True)
        print(f"state dir : {state_dir()}\nweb UI    : UNLOCKED (web_token.txt removed)")
        return
    if a.set is not None and a.set.strip():
        f.write_text(a.set.strip() + "\n", encoding="utf-8")
    elif a.rotate or (a.set is not None and not f.exists()):
        f.write_text(secrets.token_urlsafe(24) + "\n", encoding="utf-8")
    print(f"state dir : {state_dir()}")
    if f.exists():
        print(f"token     : {f.read_text(encoding='utf-8').strip()}")
        print("web UI    : LOCKED. On each device open /login once and type the token.")
    else:
        print("web UI    : open (no web_token.txt). Use --set to lock.")


if __name__ == "__main__":
    main()
