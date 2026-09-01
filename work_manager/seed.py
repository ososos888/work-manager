from pathlib import Path

import yaml

from .config import SEED_PATH
from .db import PRIORITIES, STATUSES, allow_official_writes, connect, init_db

UPSERT = """
INSERT INTO official_tasks(
  id, slug, category, title, description, created_at, due_date, status, priority,
  owner, stakeholders, local_path, discord_channel_id, discord_thread_id, notes,
  last_updated_at, next_action, is_review_excluded, source, created_by, updated_by
)
VALUES(
  :id, :slug, :category, :title, :description, COALESCE(:created_at, CURRENT_TIMESTAMP), :due_date, :status, :priority,
  :owner, :stakeholders, :local_path, :discord_channel_id, :discord_thread_id, :notes,
  COALESCE(:last_updated_at, CURRENT_TIMESTAMP), :next_action, :is_review_excluded, :source, :created_by, :updated_by
)
ON CONFLICT(id) DO UPDATE SET
  slug=excluded.slug,
  category=excluded.category,
  title=excluded.title,
  description=excluded.description,
  due_date=excluded.due_date,
  status=excluded.status,
  priority=excluded.priority,
  owner=excluded.owner,
  stakeholders=excluded.stakeholders,
  local_path=excluded.local_path,
  discord_channel_id=excluded.discord_channel_id,
  discord_thread_id=excluded.discord_thread_id,
  notes=excluded.notes,
  next_action=excluded.next_action,
  is_review_excluded=excluded.is_review_excluded,
  source=excluded.source,
  updated_by=excluded.updated_by,
  last_updated_at=CURRENT_TIMESTAMP
"""

FIELDS = [
    "id", "slug", "category", "title", "description", "created_at", "due_date", "status",
    "priority", "owner", "stakeholders", "local_path", "discord_channel_id",
    "discord_thread_id", "notes", "last_updated_at", "next_action", "is_review_excluded",
    "source", "created_by", "updated_by",
]


def normalize(task: dict) -> dict:
    row = {field: task.get(field) for field in FIELDS}
    row["id"] = int(task["id"])
    row["slug"] = row["slug"] or f"task-{row['id']}"
    row["status"] = row["status"] or "todo"
    row["priority"] = row["priority"] or "medium"
    row["is_review_excluded"] = 1 if task.get("is_review_excluded") else 0
    row["source"] = row["source"] or "seed_import"
    row["created_by"] = row["created_by"] or "seed"
    row["updated_by"] = row["updated_by"] or "seed"
    if row["status"] not in STATUSES:
        raise ValueError(f"bad status for task {row['id']}: {row['status']}")
    if row["priority"] not in PRIORITIES:
        raise ValueError(f"bad priority for task {row['id']}: {row['priority']}")
    return row


def import_seed(seed_path: Path = SEED_PATH, db_path=None) -> int:
    init_db(db_path)
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
    tasks = data.get("tasks", [])
    with allow_official_writes(), connect(db_path) as conn:
        for task in tasks:
            conn.execute(UPSERT, normalize(task))
            for link in task.get("links", []):
                conn.execute(
                    "INSERT INTO task_links(task_id, link_type, label, url) VALUES(?, ?, ?, ?)",
                    (task["id"], link.get("type", "other"), link.get("label"), link["url"]),
                )
    return len(tasks)
