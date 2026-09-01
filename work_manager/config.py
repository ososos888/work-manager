from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "work_manager.sqlite3"
REPORTS_DIR = ROOT / "reports"
BACKUPS_DIR = ROOT / "backups"
SEED_PATH = ROOT / "seeds" / "initial_tasks.yaml"
