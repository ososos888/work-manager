import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.backup import backup_db, prune_backups
from work_manager.db import allow_official_writes, connect

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an explicitly approved official-state SQL file with backup.")
    parser.add_argument("sql", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.sql.exists():
        raise SystemExit(f"missing SQL file: {args.sql}")
    sql = args.sql.read_text(encoding="utf-8")
    if not args.apply:
        print(f"dry-run: would execute {args.sql}")
        print("pass --apply after user approval")
        raise SystemExit(0)

    backup = backup_db(f"before-{args.sql.stem}")
    try:
        with allow_official_writes(args.sql.stem), connect() as conn:
            conn.executescript(sql)
    except sqlite3.Error as exc:
        raise SystemExit(f"SQL failed after backup {backup}: {exc}") from exc
    removed = prune_backups(7)
    print(f"backup: {backup}")
    print(f"applied: {args.sql}")
    if removed:
        print(f"pruned {len(removed)} old backup(s)")
