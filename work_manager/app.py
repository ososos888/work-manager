from html import escape

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .db import RECOMMENDATION_STATUSES, connect, init_db
from .review import run_daily_review

app = FastAPI(title="work-manager")

HTML = """
<!doctype html><title>work-manager</title><body>
<h1>Tasks</h1>
<form><input name=q value="{q}" placeholder=search><input name=status value="{status}" placeholder=status><input name=category value="{category}" placeholder=category><button>Filter</button></form>
<ul>{tasks}</ul>
<h2>Pending recommendations</h2><ul>{recs}</ul>
<form method=post action=/reviews/manual><button>Run daily review</button></form>
</body>
"""
DETAIL = """
<!doctype html><title>{title}</title><body><a href=/>Back</a><h1>{title}</h1>
<p>{category} / {status} / {priority}</p>
<p>due: {due_date}</p><p>next: {next_action}</p><p>{local_path}</p><p>{notes}</p>
<h2>Links</h2><ul>{links}</ul><h2>Updates</h2><ul>{updates}</ul><h2>Recommendations</h2><ul>{recs}</ul></body>
"""


def guard_localhost(request: Request):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise PermissionError("localhost only")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def index(request: Request, status: str = "", category: str = "", q: str = ""):
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
    sql = "SELECT * FROM official_tasks" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY category, id"
    with connect() as conn:
        tasks = conn.execute(sql, params).fetchall()
        recs = conn.execute("SELECT r.*, t.title task_title FROM ai_recommendations r LEFT JOIN official_tasks t ON t.id=r.task_id WHERE r.status='pending' ORDER BY r.created_at DESC").fetchall()
    task_html = "".join(f"<li>#{t['id']} <a href=/tasks/{t['id']}>{escape(t['title'])}</a> {escape(t['category'])} {escape(t['status'])} {escape(t['priority'])}</li>" for t in tasks)
    rec_html = "".join(rec_item(r) for r in recs)
    return HTML.format(tasks=task_html, recs=rec_html, status=escape(status), category=escape(category), q=escape(q))


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
def detail(request: Request, task_id: int):
    guard_localhost(request)
    with connect() as conn:
        task = conn.execute("SELECT * FROM official_tasks WHERE id=?", (task_id,)).fetchone()
        updates = conn.execute("SELECT * FROM task_updates WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall()
        recs = conn.execute("SELECT * FROM ai_recommendations WHERE task_id=? ORDER BY created_at DESC", (task_id,)).fetchall()
        links = conn.execute("SELECT * FROM task_links WHERE task_id=? ORDER BY link_type, label", (task_id,)).fetchall()
    if not task:
        return HTMLResponse("not found", status_code=404)
    return DETAIL.format(
        title=escape(task["title"]), category=escape(task["category"]), status=escape(task["status"]), priority=escape(task["priority"]),
        due_date=escape(task["due_date"] or ""), next_action=escape(task["next_action"] or ""), local_path=escape(task["local_path"] or ""),
        notes=escape(task["notes"] or ""), links="".join(f"<li>{escape(l['link_type'])}: <a href='{escape(l['url'])}'>{escape(l['label'] or l['url'])}</a></li>" for l in links),
        updates="".join(f"<li>{escape(u['created_at'])} {escape(u['source'])} {escape(u['message'] or '')}</li>" for u in updates), recs="".join(rec_item(r) for r in recs),
    )


def rec_item(r):
    return f"<li>#{r['id']} [{escape(r['severity'])}] {escape(r['title'])} - {escape(r['rationale'])} <form style='display:inline' method=post action=/recommendations/{r['id']}/decide><button name=decision value=approved>approve</button><button name=decision value=rejected>reject</button><button name=decision value=deferred>defer</button></form></li>"


@app.get("/recommendations", response_class=HTMLResponse)
def recommendations(request: Request, status: str = "pending"):
    guard_localhost(request)
    with connect() as conn:
        recs = conn.execute("SELECT * FROM ai_recommendations WHERE status=? ORDER BY created_at DESC", (status,)).fetchall()
    return "<a href=/>Back</a><h1>Recommendations</h1><ul>" + "".join(rec_item(r) for r in recs) + "</ul>"


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
    return f"<a href=/>Back</a><h1>Review {review_id}</h1><p>{escape(review['summary'])}</p><p>{escape(review['markdown_report_path'] or '')}</p>"
