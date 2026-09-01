import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.review import run_daily_review

if __name__ == "__main__":
    review_id = run_daily_review()
    print(f"daily review {review_id} complete")
