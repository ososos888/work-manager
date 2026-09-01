import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.seed import import_seed

if __name__ == "__main__":
    count = import_seed()
    print(f"imported {count} tasks")
