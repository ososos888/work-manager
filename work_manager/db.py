import sqlite3
from pathlib import Path

from . import config

STATUSES = {"todo", "active", "blocked", "waiting", "done", "dropped", "on_demand", "excluded"}
PRIORITIES = {"highest", "high", "medium", "low", "later"}
RECOMMENDATION_STATUSES = {"pending", "approved", "rejected", "deferred", "superseded"}

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS official_tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE,
  category TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  due_date TEXT,
  status TEXT NOT NULL DEFAULT 'todo',
  priority TEXT NOT NULL DEFAULT 'medium',
  owner TEXT,
  stakeholders TEXT,
  local_path TEXT,
  discord_channel_id TEXT,
  discord_thread_id TEXT,
  notes TEXT,
  last_updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  next_action TEXT,
  is_review_excluded INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'manual',
  created_by TEXT,
  updated_by TEXT,
  task_type TEXT NOT NULL DEFAULT 'task',
  parent_task_id INTEGER REFERENCES official_tasks(id) ON DELETE SET NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS task_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES official_tasks(id) ON DELETE CASCADE,
  link_type TEXT NOT NULL,
  label TEXT,
  url TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS task_work_locations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES official_tasks(id) ON DELETE CASCADE,
  location_type TEXT NOT NULL,
  label TEXT,
  uri TEXT NOT NULL,
  details TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS task_updates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL REFERENCES official_tasks(id) ON DELETE CASCADE,
  update_type TEXT NOT NULL,
  source TEXT NOT NULL,
  field_name TEXT,
  old_value TEXT,
  new_value TEXT,
  body TEXT,
  message TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_by TEXT,
  discord_message_id TEXT
);
CREATE TABLE IF NOT EXISTS ai_recommendations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER REFERENCES official_tasks(id) ON DELETE SET NULL,
  category TEXT,
  recommendation_type TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  body TEXT,
  proposed_action TEXT,
  proposed_field TEXT,
  proposed_value TEXT,
  confidence REAL,
  severity TEXT NOT NULL DEFAULT 'info',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT,
  reviewed_by TEXT,
  decision_note TEXT,
  source_snapshot TEXT,
  daily_review_id INTEGER REFERENCES daily_reviews(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS daily_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  review_date TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TEXT,
  total_tasks INTEGER NOT NULL DEFAULT 0,
  due_soon_count INTEGER NOT NULL DEFAULT 0,
  stale_count INTEGER NOT NULL DEFAULT 0,
  blocked_count INTEGER NOT NULL DEFAULT 0,
  recommendation_count INTEGER NOT NULL DEFAULT 0,
  markdown_report_path TEXT,
  discord_message_id TEXT,
  status TEXT NOT NULL DEFAULT 'running',
  error TEXT,
  discord_sent INTEGER NOT NULL DEFAULT 0,
  summary TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def migrate(conn: sqlite3.Connection) -> None:
    ensure_columns(
        conn,
        "official_tasks",
        {
            "slug": "TEXT",
            "due_date": "TEXT",
            "owner": "TEXT",
            "stakeholders": "TEXT",
            "jira_link": "TEXT",
            "confluence_link": "TEXT",
            "other_links": "TEXT",
            "discord_channel_id": "TEXT",
            "discord_thread_id": "TEXT",
            "notes": "TEXT",
            "last_updated_at": "TEXT",
            "next_action": "TEXT",
            "is_review_excluded": "INTEGER NOT NULL DEFAULT 0",
            "source": "TEXT NOT NULL DEFAULT 'manual'",
            "created_by": "TEXT",
            "updated_by": "TEXT",
            "task_type": "TEXT NOT NULL DEFAULT 'task'",
            "parent_task_id": "INTEGER REFERENCES official_tasks(id) ON DELETE SET NULL",
            "sort_order": "INTEGER NOT NULL DEFAULT 0",
        },
    )
    ensure_columns(conn, "task_links", {"link_type": "TEXT NOT NULL DEFAULT 'other'", "label": "TEXT"})
    ensure_columns(conn, "task_work_locations", {"location_type": "TEXT NOT NULL DEFAULT 'local'", "label": "TEXT", "details": "TEXT"})
    ensure_columns(conn, "task_updates", {"update_type": "TEXT", "field_name": "TEXT", "old_value": "TEXT", "new_value": "TEXT", "body": "TEXT", "message": "TEXT", "created_by": "TEXT", "discord_message_id": "TEXT"})
    ensure_columns(conn, "ai_recommendations", {"category": "TEXT", "recommendation_type": "TEXT NOT NULL DEFAULT 'risk'", "rationale": "TEXT", "proposed_action": "TEXT", "proposed_field": "TEXT", "proposed_value": "TEXT", "confidence": "REAL", "reviewed_at": "TEXT", "reviewed_by": "TEXT", "decision_note": "TEXT", "source_snapshot": "TEXT"})
    ensure_columns(conn, "daily_reviews", {"total_tasks": "INTEGER NOT NULL DEFAULT 0", "due_soon_count": "INTEGER NOT NULL DEFAULT 0", "stale_count": "INTEGER NOT NULL DEFAULT 0", "blocked_count": "INTEGER NOT NULL DEFAULT 0", "recommendation_count": "INTEGER NOT NULL DEFAULT 0", "markdown_report_path": "TEXT", "discord_message_id": "TEXT", "status": "TEXT NOT NULL DEFAULT 'running'", "error": "TEXT"})


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        migrate(conn)
        conn.execute("UPDATE official_tasks SET last_updated_at=COALESCE(last_updated_at, created_at, CURRENT_TIMESTAMP)")
        rec_cols = {row["name"] for row in conn.execute("PRAGMA table_info(ai_recommendations)")}
        if "body" in rec_cols:
            conn.execute("UPDATE ai_recommendations SET rationale=COALESCE(rationale, body, title) WHERE rationale IS NULL")
        conn.executemany(
            "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
            [
                ("dashboard_host", "127.0.0.1"),
                ("dashboard_port", "8765"),
                ("discord_enabled", "false"),
                ("discord_delivery", "origin"),
                ("daily_review_noop_discord", "false"),
            ],
        )
