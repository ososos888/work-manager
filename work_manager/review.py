import json
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import REPORTS_DIR
from .db import connect

REVIEWABLE = {"active", "todo", "blocked", "waiting", "on_demand"}
VISIBLE_SEVERITIES = {"critical", "high"}


def run_git(path: Path, args: list[str]) -> str:
    result = subprocess.run(["git", "-C", str(path), *args], text=True, capture_output=True, timeout=10)
    return result.stdout.strip() if result.returncode == 0 else ""


def scan_workspace(path: Path) -> dict:
    snapshot = {"path": str(path), "exists": path.exists(), "is_git": False}
    if not path.exists():
        return snapshot
    git_root = run_git(path, ["rev-parse", "--show-toplevel"])
    if not git_root:
        return snapshot
    status = run_git(path, ["status", "--porcelain"])
    snapshot.update(
        {
            "is_git": True,
            "git_root": git_root,
            "branch": run_git(path, ["branch", "--show-current"]) or "unknown",
            "changed_files": [line for line in status.splitlines() if line],
            "recent_commits": run_git(path, ["log", "--since=7 days ago", "--oneline", "-5"]).splitlines(),
        }
    )
    return snapshot


def task_recommendations(task, today: date) -> list[dict]:
    recs = []
    category = task["category"]
    priority = task["priority"]
    status = task["status"]
    title = task["title"]
    if task["due_date"]:
        due = date.fromisoformat(task["due_date"])
        days = (due - today).days
        if days < 0:
            recs.append(("critical", "due_soon", "Task is overdue", f"{title} is overdue by {-days} days."))
        elif days <= 3 and status not in {"done", "dropped"}:
            recs.append(("high", "due_soon", "Task is due soon", f"{title} is due in {days} days."))
    if status == "blocked" and not task["notes"]:
        recs.append(("high", "risk", "Blocked task lacks blocker note", f"{title} is blocked but has no recorded blocker."))
    if priority in {"highest", "high"} and status in {"active", "todo"} and not task["next_action"]:
        recs.append(("high", "missing_next_action", "High priority task needs next action", f"{title} has no next_action."))
    if task["last_updated_at"]:
        last = datetime.fromisoformat(task["last_updated_at"].replace("Z", "+00:00")).date()
        if status in {"active", "blocked", "waiting"} and (today - last).days >= 7:
            recs.append(("medium", "stale_task", "Task has not been updated recently", f"{title} has not changed for {(today - last).days} days."))
    if task["local_path"]:
        snapshot = scan_workspace(Path(task["local_path"]).expanduser())
        if not snapshot["exists"]:
            recs.append(("high", "risk", "Local path missing", f"{snapshot['path']} does not exist."))
        elif not snapshot["is_git"]:
            recs.append(("medium", "risk", "Workspace is not a git repo", f"{snapshot['path']} exists but git status is unavailable."))
        elif snapshot["changed_files"]:
            sev = "high" if priority in {"highest", "high"} else "medium"
            body = f"{snapshot['git_root']} on {snapshot['branch']} has {len(snapshot['changed_files'])} changed files."
            recs.append((sev, "workspace_diff", "Workspace has uncommitted changes", body, snapshot))
        elif priority in {"highest", "high"} and status == "active" and not snapshot["recent_commits"]:
            recs.append(("medium", "stale_task", "No recent commits in workspace", f"{title} has no commits in the last 7 days.", snapshot))
    out = []
    for rec in recs:
        severity, rec_type, rec_title, rationale, *snapshot = rec
        out.append(
            {
                "task_id": task["id"],
                "category": category,
                "recommendation_type": rec_type,
                "title": rec_title,
                "rationale": rationale,
                "proposed_action": rationale,
                "proposed_field": "next_action" if rec_type in {"missing_next_action", "workspace_diff"} else None,
                "proposed_value": rationale if rec_type in {"missing_next_action", "workspace_diff"} else None,
                "confidence": 0.8,
                "severity": severity,
                "source_snapshot": json.dumps(snapshot[0], ensure_ascii=False) if snapshot else None,
            }
        )
    return out


def task_line(task) -> str:
    due = f" · due {task['due_date']}" if task['due_date'] else ""
    action = f" — next: {task['next_action']}" if task['next_action'] else ""
    return f"- #{task['id']} [{task['priority']}] {task['category']} · {task['title']}{due}{action}"


def task_section(title: str, tasks: list) -> list[str]:
    lines = [f"## {title}", ""]
    if not tasks:
        return lines + ["None.", ""]
    return lines + [task_line(task) for task in tasks] + [""]


def write_report(review_id: int, today: str, tasks: list, created: list[tuple], skipped_duplicates: int) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORTS_DIR / f"daily-review-{today}-{review_id}.md"
    lines = [
        f"# Daily Review {today}",
        "",
        f"Reviewed tasks: {len(tasks)}",
        f"New recommendations: {len(created)}",
        f"Duplicate pending recommendations skipped: {skipped_duplicates}",
        "",
    ]
    active = [task for task in tasks if task["status"] in {"active", "blocked", "waiting"}]
    not_started = [task for task in tasks if task["status"] in {"todo", "on_demand"}]
    done = [task for task in tasks if task["status"] == "done"]
    lines.extend(task_section("In progress", active))
    lines.extend(task_section("Not started / on demand", not_started))
    lines.extend(task_section("Done", done))
    if not created:
        lines.append("No new recommendations.")
        lines.append("")
    for task, rec in created:
        lines += [f"## {rec['severity']} · {task['category']} · {task['title']}", "", rec["title"], "", rec["rationale"], ""]
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def has_pending_duplicate(conn, rec: dict) -> bool:
    return conn.execute(
        """
        SELECT 1 FROM ai_recommendations
        WHERE status='pending'
          AND task_id IS ?
          AND recommendation_type=?
          AND rationale=?
        LIMIT 1
        """,
        (rec["task_id"], rec["recommendation_type"], rec["rationale"]),
    ).fetchone() is not None


def insert_recommendation(conn, rec: dict, review_id: int) -> int | None:
    if has_pending_duplicate(conn, rec):
        return None
    cur = conn.execute(
        """
        INSERT INTO ai_recommendations(
          task_id, category, recommendation_type, title, rationale, body, proposed_action,
          proposed_field, proposed_value, confidence, severity, source_snapshot, daily_review_id
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rec["task_id"], rec["category"], rec["recommendation_type"], rec["title"], rec["rationale"], rec["rationale"],
            rec["proposed_action"], rec["proposed_field"], rec["proposed_value"], rec["confidence"],
            rec["severity"], rec["source_snapshot"], review_id,
        ),
    )
    return cur.lastrowid


def run_daily_review(db_path=None) -> int:
    today = date.today()
    with connect(db_path) as conn:
        cur = conn.execute("INSERT INTO daily_reviews(review_date) VALUES(?)", (today.isoformat(),))
        review_id = cur.lastrowid
        tasks = conn.execute(
            "SELECT * FROM official_tasks WHERE status IN ({}) AND is_review_excluded=0".format(",".join("?" for _ in REVIEWABLE)),
            tuple(REVIEWABLE),
        ).fetchall()
        report_tasks = conn.execute(
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
            SELECT * FROM tree ORDER BY tree_path
            """
        ).fetchall()
        created = []
        due_soon = stale = blocked = skipped_duplicates = 0
        for task in tasks:
            if task["status"] in {"blocked", "waiting"}:
                blocked += 1
            for rec in task_recommendations(task, today):
                if rec["recommendation_type"] == "due_soon":
                    due_soon += 1
                if rec["recommendation_type"] == "stale_task":
                    stale += 1
                rec_id = insert_recommendation(conn, rec, review_id)
                if rec_id is None:
                    skipped_duplicates += 1
                    continue
                created.append((task, {**rec, "id": rec_id}))
        report = write_report(review_id, today.isoformat(), report_tasks, created, skipped_duplicates)
        discord_should_send = any(rec["severity"] in VISIBLE_SEVERITIES for _, rec in created)
        summary = f"{len(created)} new recommendations; {skipped_duplicates} duplicates skipped; discord {'ready' if discord_should_send else 'skipped'}"
        conn.execute(
            """
            UPDATE daily_reviews
            SET finished_at=CURRENT_TIMESTAMP, total_tasks=?, due_soon_count=?, stale_count=?, blocked_count=?,
                recommendation_count=?, markdown_report_path=?, status='success', discord_sent=0, summary=?
            WHERE id=?
            """,
            (len(tasks), due_soon, stale, blocked, len(created), str(report) if report else None, summary, review_id),
        )
    return review_id
