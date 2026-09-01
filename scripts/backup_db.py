import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.backup import backup_db, prune_backups

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a SQLite DB backup and prune old backups.")
    parser.add_argument("--reason", default="manual")
    parser.add_argument("--retention-days", type=int, default=7)
    args = parser.parse_args()

    target = backup_db(args.reason)
    removed = prune_backups(args.retention_days)
    print(target)
    if removed:
        print(f"pruned {len(removed)} old backup(s)")
