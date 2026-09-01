from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

from .config import DB_PATH, ROOT

DASHBOARD_URL = 'http://127.0.0.1:8765'
PRIORITY_RANK = {'highest': 0, 'high': 1, 'medium': 2, 'low': 3, 'later': 4}


def task_line(row):
    due = f" · due {row['due_date']}" if row['due_date'] else ''
    action = f" — next: {row['next_action']}" if row['next_action'] else ''
    prefix = '↳ ' * row['depth']
    return f"- {prefix}#{row['id']} [{row['priority']}] {row['category']} · {row['title']}{due}{action}"


def rec_line(row):
    return f"- #{row['id']} [{row['severity']}] {row['category']} · {row['title']} — {row['rationale']}"


def days_until(row):
    return 9999 if row['days_until_due'] is None else row['days_until_due']


def rank(row):
    return (days_until(row), PRIORITY_RANK.get(row['priority'], 9), row['tree_path'])


def add_section(lines, title, rows, formatter):
    lines.append('')
    lines.append(f'{title}:')
    if rows:
        lines.extend(formatter(row) for row in rows)
    else:
        lines.append('- None')


def main() -> None:
    subprocess.run(['uv', 'run', 'python', 'scripts/init_db.py'], cwd=ROOT, check=True, capture_output=True, text=True)
    result = subprocess.run(['uv', 'run', 'python', 'scripts/daily_review.py'], cwd=ROOT, check=True, capture_output=True, text=True)
    review_id = int(result.stdout.strip().split()[2])
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        review = conn.execute('SELECT * FROM daily_reviews WHERE id=?', (review_id,)).fetchone()
        pending = conn.execute("SELECT COUNT(*) c FROM ai_recommendations WHERE status='pending'").fetchone()['c']
        all_tasks = conn.execute(
            """
            WITH RECURSIVE tree AS (
              SELECT official_tasks.*, printf('%06d.%06d', COALESCE(sort_order, 0), id) AS tree_path, 0 AS depth
              FROM official_tasks
              WHERE parent_task_id IS NULL AND status!='dropped'
              UNION ALL
              SELECT child.*, tree.tree_path || '.' || printf('%06d.%06d', COALESCE(child.sort_order, 0), child.id), tree.depth + 1
              FROM official_tasks child
              JOIN tree ON child.parent_task_id = tree.id
              WHERE child.status!='dropped' AND child.is_review_excluded=0
            )
            SELECT *, CAST(julianday(due_date) - julianday('now', 'localtime') AS INTEGER) AS days_until_due
            FROM tree ORDER BY tree_path
            """
        ).fetchall()
        top_recs = conn.execute(
            """
            SELECT r.id, r.severity, COALESCE(t.category, r.category) category, r.title, r.rationale
            FROM ai_recommendations r
            LEFT JOIN official_tasks t ON t.id=r.task_id
            WHERE r.status='pending'
            ORDER BY CASE r.severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, r.created_at DESC
            LIMIT 5
            """
        ).fetchall()
    urgent = [row for row in all_tasks if row['status'] != 'done' and row['days_until_due'] is not None and row['days_until_due'] <= 7]
    remaining = [row for row in all_tasks if row['status'] in {'active', 'blocked', 'waiting', 'todo', 'on_demand'} and row not in urgent]
    done = [row for row in all_tasks if row['status'] == 'done']
    urgent = sorted(urgent, key=rank)
    remaining = sorted(remaining, key=lambda row: (PRIORITY_RANK.get(row['priority'], 9), row['tree_path']))
    lines = [
        f"work-manager daily review #{review_id}",
        f"dashboard: {DASHBOARD_URL}",
        f"summary: reviewed {review['total_tasks']}, new recs {review['recommendation_count']}, pending recs {pending}",
    ]
    if review['markdown_report_path']:
        lines.append(f"report: {review['markdown_report_path']}")
    add_section(lines, 'Deadline / due soon first', urgent, task_line)
    add_section(lines, 'Other active or not-started work', remaining, task_line)
    add_section(lines, 'High-priority AI recommendations', top_recs, rec_line)
    add_section(lines, 'Done', done, task_line)
    print('\n'.join(lines))
