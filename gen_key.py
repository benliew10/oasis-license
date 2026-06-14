#!/usr/bin/env python3
"""Generate Oasis license keys and add them to licenses.json."""
from __future__ import annotations

import argparse
import json
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LICENSES_PATH = ROOT / "licenses.json"
PREFIX = "Oas01"
KEY_CHARS = string.ascii_letters + string.digits


def load_db() -> dict:
    if LICENSES_PATH.exists():
        return json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    return {}


def save_db(data: dict) -> None:
    LICENSES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def make_key(length: int = 32) -> str:
    # Total key length including prefix; anubis sends key + _iOS4.4.0
    need = max(8, length - len(PREFIX))
    tail = "".join(secrets.choice(KEY_CHARS) for _ in range(need))
    return PREFIX + tail


def default_expire(days: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=days)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    p = argparse.ArgumentParser(description="Generate Oasis license keys")
    p.add_argument("-n", "--count", type=int, default=1)
    p.add_argument("--days", type=int, default=365, help="Validity in days")
    p.add_argument("--category", default="default")
    p.add_argument("--length", type=int, default=32, help="Total key length")
    p.add_argument("--list", action="store_true", help="List existing keys")
    args = p.parse_args()

    db = load_db()

    if args.list:
        for k, v in sorted(db.items()):
            print(f"{k}\texpire={v.get('expire')}\tcategory={v.get('businessCategory')}")
        return

    created = []
    for _ in range(args.count):
        key = make_key(args.length)
        while key in db:
            key = make_key(args.length)
        db[key] = {
            "expire": default_expire(args.days),
            "businessCategory": args.category,
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        created.append(key)

    save_db(db)
    for key in created:
        print(key)
    print(f"\nSaved {len(created)} key(s) -> {LICENSES_PATH}", file=__import__("sys").stderr)


if __name__ == "__main__":
    main()
