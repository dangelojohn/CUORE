"""CLI: python -m cuore.accounts <create-admin|add-user|disable|list|enable-mode|disable-mode>.

Passwords are read with getpass (never an argument). Works on the state dir
CUORE_STATE_DIR points at, else the default.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .services import accounts


def _password() -> str:
    p1 = getpass.getpass("Password: ")
    if p1 != getpass.getpass("Repeat password: "):
        raise accounts.AccountError("passwords do not match")
    return p1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cuore.accounts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("create-admin", "add-user"):
        s = sub.add_parser(name)
        s.add_argument("--username", required=True)
        s.add_argument("--display-name", default="")
        s.add_argument("--shop-id", default="main")
        s.add_argument("--shop-kind", choices=accounts.SHOP_KINDS, default="independent")
        if name == "add-user":
            s.add_argument("--role", choices=("shop_lead", "technician"), default="technician")
    s = sub.add_parser("disable")
    s.add_argument("--username", required=True)
    sub.add_parser("list")
    sub.add_parser("enable-mode")
    sub.add_parser("disable-mode")
    a = ap.parse_args(argv)
    try:
        if a.cmd in ("create-admin", "add-user"):
            role = "admin" if a.cmd == "create-admin" else a.role
            u = accounts.create(a.username, _password(), role, a.display_name, a.shop_id, a.shop_kind)
            print(f"created {u['role']} '{u['username']}' (shop {u['shop_id']}). "
                  f"Accounts mode is {'ON' if accounts.mode_active() else 'OFF'}; "
                  "run enable-mode to turn it on.")
        elif a.cmd == "disable":
            accounts.disable(a.username)
            print(f"disabled '{a.username}'")
        elif a.cmd == "list":
            for u in accounts.list_users():
                print(f"{u['username']:20} {u['role']:11} {u['shop_id']:12} {u['shop_kind']:12}"
                      f"{' DISABLED' if u['disabled'] else ''}")
            print(f"accounts mode: {'ON' if accounts.mode_active() else 'OFF'}")
        elif a.cmd == "enable-mode":
            accounts.set_mode(True)
            print("accounts mode ON")
        elif a.cmd == "disable-mode":
            accounts.set_mode(False)
            print("accounts mode OFF (shared token only)")
    except accounts.AccountError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
