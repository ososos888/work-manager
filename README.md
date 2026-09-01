# work-manager

Localhost-only FastAPI + SQLite MVP for official tasks, explicit updates, AI recommendations, and daily reviews.

## Setup

```bash
git clone https://github.com/<owner>/work-manager.git
cd work-manager
uv sync
uv run python scripts/init_db.py
uv run python scripts/import_seed.py
```

## Run dashboard

```bash
uv run uvicorn work_manager.app:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765.

## Daily review

```bash
uv run python scripts/daily_review.py
```

Daily review checks official tasks, due dates, stale active work, missing next actions, blocked items, and light local workspace state: path existence, git branch, uncommitted files, and recent commits. It writes pending `ai_recommendations`, records `daily_reviews`, and writes Markdown reports. It does not mutate official tasks.

## Backup

```bash
uv run python scripts/backup_db.py
uv run python scripts/list_backups.py
uv run python scripts/restore_backup.py backups/<file>.sqlite3 --apply
uv run python scripts/apply_official_sql.py tmp/update.sql --apply
```

Official task-state tables are locked by default. Use `apply_official_sql.py --apply` only after explicit user approval; it creates a backup and prunes backups older than seven days. AI recommendation and daily review tables remain writable for automation.

## Test

```bash
uv run pytest
uv run python -m compileall work_manager scripts
```

## Data

- SQLite: `data/work_manager.sqlite3`
- Seed YAML: `seeds/initial_tasks.yaml`
- Reports: `reports/`
- Backups: `backups/`

## Initial design decisions

- Personal local-only operation.
- Dashboard binds to `127.0.0.1`.
- Discord natural language is the primary future command surface.
- Official task state is stored separately from pending AI recommendations.
- AI recommendations require approval before official task mutation.
