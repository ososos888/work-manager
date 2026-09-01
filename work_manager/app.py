from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .db import RECOMMENDATION_STATUSES, allow_official_writes, connect, init_db
from .review import run_daily_review

app = FastAPI(title="work-manager")

STYLE = """
<style>
:root { color-scheme: light; --bg:#f6f7fb; --card:#fff; --muted:#667085; --line:#e6e8ef; --text:#172033; --brand:#315efb; --ok:#087443; --warn:#b54708; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
a { color:var(--brand); text-decoration:none; } a:hover { text-decoration:underline; }
.wrap { max-width:1100px; margin:0 auto; padding:28px; }
.header { display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom:20px; }
h1 { margin:0; font-size:28px; letter-spacing:-.03em; } h2 { margin:24px 0 12px; font-size:17px; }
.subtle { color:var(--muted); }
.card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; box-shadow:0 1px 2px rgba(16,24,40,.04); }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; }
.toolbar { display:grid; grid-template-columns:1fr 140px 160px auto auto; gap:8px; align-items:center; margin-bottom:14px; }
input, select, button { border:1px solid var(--line); border-radius:10px; padding:9px 10px; background:white; font:inherit; }
button, .btn { display:inline-block; background:var(--brand); border-color:var(--brand); color:white; border-radius:10px; padding:9px 12px; cursor:pointer; }
.btn.secondary, button.secondary { background:white; color:var(--text); border-color:var(--line); }
.task { display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:start; padding:13px 0; border-top:1px solid var(--line); }
.task.child { margin-left:28px; border-left:2px solid var(--line); padding-left:12px; }
.task:first-child { border-top:0; }
.id { color:var(--muted); font-variant-numeric:tabular-nums; }
.title { font-weight:650; }
.meta { margin-top:5px; color:var(--muted); font-size:13px; }
.pills { display:flex; gap:6px; flex-wrap:wrap; justify-content:flex-end; }
.pill { border-radius:999px; padding:3px 8px; font-size:12px; background:#eef2ff; color:#3538cd; white-space:nowrap; }
.pill.active { background:#ecfdf3; color:var(--ok); }
.pill.todo { background:#fff7ed; color:var(--warn); }
.pill.done { background:#f2f4f7; color:#475467; }
.pill.seed { background:#f2f4f7; color:#475467; }
.pill.epic { background:#f4ebff; color:#6941c6; }
.list { list-style:none; margin:0; padding:0; }
.row { padding:10px 0; border-top:1px solid var(--line); }
.row:first-child { border-top:0; }
.kv { display:grid; grid-template-columns:130px 1fr; gap:8px; margin:8px 0; }
.empty { color:var(--muted); padding:14px 0; }
.form-row { display:grid; grid-template-columns:140px 1fr 1fr 1.5fr auto; gap:8px; }
@media (max-width:760px) { .toolbar,.form-row { grid-template-columns:1fr; } .task { grid-template-columns:1fr; } .pills { justify-content:flex-start; } .header { display:block; } }
</style>
"""

HTML = """
<!doctype html><html><head><meta charset="utf-8"><title>work-manager</title>{style}</head><body><main class="wrap">
<div class="header"><div><h1>Work manager</h1><div class="subtle">Local task dashboard · official updates and AI recommendations are separated</div></div><form method="post" action="/reviews/manual"><button>Run daily review</button></form></div>
<section class="card">
<form class="toolbar"><input name="q" value="{q}" placeholder="Search title"><input name="status" value="{status}" placeholder="status"><input name="category" value="{category}" placeholder="category"><select name="source"><option value="non_seed" {source_non_seed}>registered only</option><option value="all" {source_all}>all tasks</option><option value="seed" {source_seed}>seed only</option></select><button>Filter</button></form>
<div class="subtle">Showing {count} active/open task(s). 기본은 사용자가 등록/수정한 업무만 보이도록 seed_import 항목을 숨깁니다.</div>
<div class="list">{tasks}</div>
</section>
<section class="card" style="margin-top:16px"><h2>Done</h2><div class="subtle">완료된 업무를 하이라키 깊이를 유지해 따로 모읍니다.</div><div class="list">{done_tasks}</div></section>
<section class="card" style="margin-top:16px"><h2>Pending recommendations</h2><div class="list">{recs}</div></section>
</main></body></html>
"""

DETAIL = """
<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>{style}</head><body><main class="wrap">
<div class="header"><div><a href="/">← Back</a><h1>{title}</h1><div class="subtle">#{task_id} · {category} · {task_type}</div></div><div class="pills"><span class="pill {task_type_class}">{task_type}</span><span class="pill {status}">{status}</span><span class="pill">{priority}</span><span class="pill">due {due_date}</span></div></div>
<section class="card"><div class="kv"><b>Next action</b><div>{next_action}</div><b>Local path</b><div>{local_path}</div><b>Notes</b><div>{notes}</div></div></section>
<section class="card" style="margin-top:16px"><h2>Work locations</h2><ul class="list">{locations}</ul><form class="form-row" method="post" action="/tasks/{task_id}/work-locations"><input name="location_type" placeholder="local/container/server" required><input name="label" placeholder="label"><input name="uri" placeholder="file://, ssh://, vscode://, https://" required><input name="details" placeholder="details"><button>Add</button></form></section>
<section class="grid" style="margin-top:16px"><div class="card"><h2>Links</h2><ul class="list">{links}</ul></div><div class="card"><h2>Recommendations</h2><ul class="list">{recs}</ul></div></section>
<section class="card" style="margin-top:16px"><h2>Updates</h2><ul class="list">{updates}</ul></section>
</main></body></html>
"""


def guard_localhost(request: Request):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise PermissionError("localhost only")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, status: str = "", category: str = "", q: str = "", source: str = "non_seed"):
    guard_localhost(request)
    where, params = [], []
    if status:
        where.append("status=?")
        params.append(status)
    if category:
        where.append("category=?")
        params.append(category)
    if q:
        where.append("title LIKE ?")
        params.append(f"%{q}%")
    if source == "non_seed":
        where.append("source != 'seed_import'")
    elif source == "seed":
        where.append("source = 'seed_import'")
    base_sql = "SELECT * FROM official_tasks" + (" WHERE " + " AND ".join(where) if where else "")
    sql = f"""
    WITH RECURSIVE filtered AS ({base_sql}),
    tree AS (
      SELECT filtered.*, printf('%06d.%06d', COALESCE(sort_order, 0), id) AS tree_path, 0 AS depth
      FROM filtered
      WHERE parent_task_id IS NULL
      UNION ALL
      SELECT child.*, tree.tree_path || '.' || printf('%06d.%06d', COALESCE(child.sort_order, 0), child.id), tree.depth + 1
      FROM filtered child
      JOIN tree ON child.parent_task_id = tree.id
    )
    SELECT * FROM tree ORDER BY tree_path
    """
    with connect() as conn:
        all_tasks = conn.execute(sql, params).fetchall()
        recs = conn.execute("SELECT r.*, t.title task_title FROM ai_recommendations r LEFT JOIN official_tasks t ON t.id=r.task_id WHERE r.status='pending' ORDER BY r.created_at DESC").fetchall()
    tasks = [t for t in all_tasks if t["status"] != "done"]
    done_tasks = [t for t in all_tasks if t["status"] == "done"]
    task_html = "".join(task_item(t) for t in tasks) or '<div class="empty">No tasks</div>'
    done_html = "".join(task_item(t) for t in done_tasks) or '<div class="empty">No done tasks</div>'
    rec_html = "".join(rec_item(r) for r in recs) or '<div class="empty">No pending recommendations</div>'
    return HTML.format(
        style=STYLE, tasks=task_html, done_tasks=done_html, recs=rec_html, count=len(tasks),
        status=escape(status), category=escape(category), q=escape(q),
        source_non_seed="selected" if source == "non_seed" else "",
        source_all="selected" if source == "all" else "",
        source_seed="selected" if source == "seed" else "",
    )


def task_item(t):
    source_badge = '<span class="pill seed">seed</span>' if t["source"] == "seed_import" else ""
    type_badge = '<span class="pill epic">epic</span>' if "task_type" in t.keys() and t["task_type"] == "epic" else ""
    due = f" · due {escape(t['due_date'])}" if t["due_date"] else ""
    next_action = f" · {escape(t['next_action'])}" if t["next_action"] else ""
    depth = t["depth"] if "depth" in t.keys() else (1 if "parent_task_id" in t.keys() and t["parent_task_id"] else 0)
    child_class = " child" if depth else ""
    prefix = "↳ " * depth
    indent = f' style="margin-left:{min(depth, 4) * 28}px"' if depth else ""
    return (
        f'<div class="task{child_class}"{indent}><div class="id">#{t["id"]}</div><div><a class="title" href="/tasks/{t["id"]}">{prefix}{escape(t["title"])}</a>'
        f'<div class="meta">{escape(t["category"])}{due}{next_action}</div></div>'
        f'<div class="pills">{type_badge}<span class="pill {escape(t["status"])}">{escape(t["status"])}</span><span class="pill">{escape(t["priority"])}</span>{source_badge}</div></div>'
    )


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def detail(request: Request, task_id: int):
    guard_localhost(request)
    with connect() as conn:
        task = conn.execute("SELECT * FROM official_tasks WHERE id=?", (task_id,)).fetchone()
        parent = conn.execute("SELECT id, title FROM official_tasks WHERE id=(SELECT parent_task_id FROM official_tasks WHERE id=?)", (task_id,)).fetchone()
        children = conn.execute("SELECT id, title, status, priority, due_date FROM official_tasks WHERE parent_task_id=? ORDER BY sort_order, id", (task_id,)).fetchall()
        updates = conn.execute("SELECT * FROM task_updates WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall()
        recs = conn.execute("SELECT * FROM ai_recommendations WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall()
        links = conn.execute("SELECT * FROM task_links WHERE task_id=? ORDER BY link_type, label", (task_id,)).fetchall()
        locations = conn.execute("SELECT * FROM task_work_locations WHERE task_id=? ORDER BY location_type, label", (task_id,)).fetchall()
    if not task:
        return HTMLResponse("not found", status_code=404)
    return DETAIL.format(
        style=STYLE, task_id=task_id, title=escape(task["title"]), category=escape(task["category"]), status=escape(task["status"]), priority=escape(task["priority"]),
        task_type=escape(task["task_type"] if "task_type" in task.keys() else "task"), task_type_class="epic" if "task_type" in task.keys() and task["task_type"] == "epic" else "",
        due_date=escape(task["due_date"] or "-"), next_action=escape(task["next_action"] or "-"), local_path=escape(task["local_path"] or "-"),
        notes=escape(((f"Parent: #{parent['id']} {parent['title']}\n" if parent else "") + ("Children: " + ", ".join(f"#{c['id']} {c['title']}" for c in children) + "\n" if children else "") + (task["notes"] or "-"))),
        locations="".join(f"<li class='row'>{escape(loc['location_type'])}: <a href='{escape(loc['uri'])}'>{escape(loc['label'] or loc['uri'])}</a> <span class='subtle'>{escape(loc['details'] or '')}</span></li>" for loc in locations) or '<li class="empty">No work locations</li>',
        links="".join(f"<li class='row'>{escape(l['link_type'])}: <a href='{escape(l['url'])}'>{escape(l['label'] or l['url'])}</a></li>" for l in links) or '<li class="empty">No links</li>',
        updates="".join(f"<li class='row'>{escape(u['created_at'])} · {escape(u['source'])} · {escape(u['message'] or u['body'] or '')}</li>" for u in updates) or '<li class="empty">No updates</li>',
        recs="".join(rec_item(r) for r in recs) or '<li class="empty">No recommendations</li>',
    )


@app.post("/tasks/{task_id}/work-locations")
def add_work_location(
    request: Request,
    task_id: int,
    location_type: str = Form(...),
    label: str = Form(""),
    uri: str = Form(...),
    details: str = Form(""),
):
    guard_localhost(request)
    with allow_official_writes("dashboard-work-location"), connect() as conn:
        task = conn.execute("SELECT id FROM official_tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            return HTMLResponse("not found", status_code=404)
        conn.execute(
            "INSERT INTO task_work_locations(task_id, location_type, label, uri, details) VALUES(?, ?, ?, ?, ?)",
            (task_id, location_type.strip(), label.strip() or None, uri.strip(), details.strip() or None),
        )
        message = f"Added work location: {location_type.strip()} {label.strip() or uri.strip()}"
        conn.execute(
            "INSERT INTO task_updates(task_id, update_type, source, body, field_name, new_value, message, created_by) VALUES(?, 'location', 'dashboard', ?, 'work_location', ?, ?, 'dashboard')",
            (task_id, message, uri.strip(), message),
        )
        conn.execute("UPDATE official_tasks SET last_updated_at=CURRENT_TIMESTAMP, updated_by='dashboard' WHERE id=?", (task_id,))
    return RedirectResponse(f"/tasks/{task_id}", status_code=303)


def rec_item(r):
    return f"<li class='row'>#{r['id']} <span class='pill'>{escape(r['severity'])}</span> <b>{escape(r['title'])}</b><div class='subtle'>{escape(r['rationale'])}</div><form method='post' action='/recommendations/{r['id']}/decide'><button name=decision value=approved>approve</button> <button class='secondary' name=decision value=rejected>reject</button> <button class='secondary' name=decision value=deferred>defer</button></form></li>"


@app.get("/recommendations", response_class=HTMLResponse)
def recommendations(request: Request, status: str = "pending"):
    guard_localhost(request)
    with connect() as conn:
        recs = conn.execute("SELECT * FROM ai_recommendations WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Recommendations</title>{STYLE}</head><body><main class='wrap'><a href='/'>← Back</a><h1>Recommendations</h1><section class='card'><ul class='list'>" + "".join(rec_item(r) for r in recs) + "</ul></section></main></body></html>"


@app.post("/recommendations/{rec_id}/decide")
def decide(request: Request, rec_id: int, decision: str = Form(...)):
    guard_localhost(request)
    if decision not in RECOMMENDATION_STATUSES - {"pending", "superseded"}:
        return HTMLResponse("bad decision", status_code=400)
    with connect() as conn:
        conn.execute("UPDATE ai_recommendations SET status=?, reviewed_at=CURRENT_TIMESTAMP, reviewed_by='dashboard' WHERE id=?", (decision, rec_id))
    return RedirectResponse("/", status_code=303)


@app.post("/reviews/manual")
def manual_review(request: Request):
    guard_localhost(request)
    review_id = run_daily_review()
    return RedirectResponse(f"/reviews/{review_id}", status_code=303)


@app.get("/reviews/{review_id}", response_class=HTMLResponse)
def review_detail(request: Request, review_id: int):
    guard_localhost(request)
    with connect() as conn:
        review = conn.execute("SELECT * FROM daily_reviews WHERE id=?", (review_id,)).fetchone()
    if not review:
        return HTMLResponse("not found", status_code=404)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Review {review_id}</title>{STYLE}</head><body><main class='wrap'><a href='/'>← Back</a><h1>Review {review_id}</h1><section class='card'><p>{escape(review['summary'])}</p><p>{escape(review['markdown_report_path'] or '')}</p></section></main></body></html>"
