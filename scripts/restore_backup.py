import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.backup import backup_db
from work_manager.config import DB_PATH

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Restore a SQLite DB backup. Dry-run by default.")
    parser.add_argument("backup", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if not args.backup.exists():
        raise SystemExit(f"missing backup: {args.backup}")
    if not args.apply:
        print(f"dry-run: would restore {args.backup} -> {DB_PATH}")
        print("pass --apply to restore")
        raise SystemExit(0)

    before = backup_db("pre-restore")
    shutil.copy2(args.backup, DB_PATH)
    print(f"saved current DB: {before}")
    print(f"restored: {args.backup} -> {DB_PATH}")
