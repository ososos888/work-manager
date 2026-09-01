from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.db import allow_official_writes, connect, init_db

VALID_TYPES = {"local", "server", "container", "compose", "vscode"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register a work location for a work-manager task.")
    parser.add_argument("--task-id", type=int, required=True)
    parser.add_argument("--type", choices=sorted(VALID_TYPES), required=True)
    parser.add_argument("--label", default="")
    parser.add_argument("--uri", required=True)
    parser.add_argument("--details", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    init_db()
    with allow_official_writes("register-location"), connect() as conn:
        task = conn.execute("SELECT id, title FROM official_tasks WHERE id=?", (args.task_id,)).fetchone()
        if not task:
            print(f"missing task id: {args.task_id}", file=sys.stderr)
            return 2
        conn.execute(
            """
            INSERT INTO task_work_locations(task_id, location_type, label, uri, details)
            VALUES(?, ?, ?, ?, ?)
            """,
            (args.task_id, args.type, args.label or None, args.uri, args.details or None),
        )
        conn.execute(
            """
            INSERT INTO task_updates(task_id, update_type, source, body, message, created_by)
            VALUES(?, 'location', 'script', ?, ?, 'register_location.py')
            """,
            (args.task_id, f"registered {args.type} location: {args.uri}", f"location registered for #{args.task_id}"),
        )
    print(f"registered {args.type} location for #{args.task_id}: {args.uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
