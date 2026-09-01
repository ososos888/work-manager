import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.backup import list_backups

if __name__ == "__main__":
    for path in list_backups():
        stat = path.stat()
        print(f"{path}\t{stat.st_size} bytes")
