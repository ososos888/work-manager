from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .config import BACKUPS_DIR, DB_PATH


def backup_db(reason: str = "manual", db_path: Path = DB_PATH, backups_dir: Path = BACKUPS_DIR) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        raise FileNotFoundError(f"missing database: {db_path}")
    safe_reason = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in reason).strip("-") or "manual"
    target = backups_dir / f"work_manager-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe_reason}.sqlite3"
    shutil.copy2(db_path, target)
    return target


def prune_backups(retention_days: int = 7, backups_dir: Path = BACKUPS_DIR) -> list[Path]:
    cutoff = datetime.now() - timedelta(days=retention_days)
    removed = []
    for path in sorted(backups_dir.glob("*.sqlite3")):
        if datetime.fromtimestamp(path.stat().st_mtime) < cutoff:
            path.unlink()
            removed.append(path)
    return removed


def list_backups(backups_dir: Path = BACKUPS_DIR) -> list[Path]:
    return sorted(backups_dir.glob("*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
