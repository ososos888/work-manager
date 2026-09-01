from pathlib import Path

from fastapi.testclient import TestClient

from work_manager.app import app
from work_manager.db import connect, init_db
from work_manager.review import run_daily_review
from work_manager.seed import import_seed


def test_seed_schema_and_review(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    seed = Path("seeds/initial_tasks.yaml")
    assert import_seed(seed, db_path) == 16
    review_id = run_daily_review(db_path)
    with connect(db_path) as conn:
        task = conn.execute("SELECT * FROM official_tasks WHERE id=16").fetchone()
        review = conn.execute("SELECT * FROM daily_reviews WHERE id=?", (review_id,)).fetchone()
        recs = conn.execute("SELECT COUNT(*) c FROM ai_recommendations WHERE status='pending'").fetchone()["c"]
    assert task["next_action"]
    assert task["status"] == "todo"
    assert review["status"] == "success"
    assert review["discord_sent"] == 0
    assert recs >= 1
    run_daily_review(db_path)
    with connect(db_path) as conn:
        recs_after_repeat = conn.execute("SELECT COUNT(*) c FROM ai_recommendations WHERE status='pending'").fetchone()["c"]
        latest = conn.execute("SELECT summary, recommendation_count, markdown_report_path FROM daily_reviews ORDER BY id DESC LIMIT 1").fetchone()
    assert recs_after_repeat == recs
    assert latest["recommendation_count"] == 0
    assert "duplicates skipped" in latest["summary"]
    report_path = Path(latest["markdown_report_path"])
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "## In progress" in report_text
    assert "## Not started / on demand" in report_text
    assert "No new recommendations" in report_text


def test_dashboard_decision(tmp_path, monkeypatch):
    import work_manager.config as config

    test_db = tmp_path / "app.sqlite3"
    monkeypatch.setattr(config, "DB_PATH", test_db)
    init_db(test_db)
    with connect(test_db) as conn:
        conn.execute("INSERT INTO official_tasks(id,category,title,status,priority) VALUES(1,'cat','X','todo','high')")
        conn.execute(
            "INSERT INTO ai_recommendations(task_id,category,recommendation_type,severity,title,rationale) VALUES(1,'cat','risk','high','Do X','Body')"
        )
        rec_id = conn.execute("SELECT id FROM ai_recommendations").fetchone()["id"]
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/tasks/1").status_code == 200
    assert client.post(
        "/tasks/1/work-locations",
        data={"location_type": "local", "label": "repo", "uri": "file:///tmp/repo", "details": "main workspace"},
        follow_redirects=False,
    ).status_code == 303
    assert client.post(f"/recommendations/{rec_id}/decide", data={"decision": "approved"}, follow_redirects=False).status_code == 303
    with connect(test_db) as conn:
        assert conn.execute("SELECT status FROM ai_recommendations WHERE id=?", (rec_id,)).fetchone()["status"] == "approved"
        loc = conn.execute("SELECT * FROM task_work_locations WHERE task_id=1").fetchone()
    assert loc["location_type"] == "local"
    assert loc["uri"] == "file:///tmp/repo"
