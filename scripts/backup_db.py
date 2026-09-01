import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.config import BACKUPS_DIR, DB_PATH

if __name__ == "__main__":
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    if not DB_PATH.exists():
        raise SystemExit(f"missing database: {DB_PATH}")
    target = BACKUPS_DIR / f"work_manager-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    shutil.copy2(DB_PATH, target)
    print(target)
