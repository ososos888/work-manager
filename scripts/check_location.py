from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from work_manager.db import connect, init_db


def run(cmd: list[str], timeout: int = 15) -> tuple[int, str]:
    proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    return proc.returncode, proc.stdout.strip()


def check_uri(uri: str) -> tuple[bool, str]:
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path = Path(parsed.path)
        return path.exists(), f"local path {'exists' if path.exists() else 'missing'}: {path}"
    if parsed.scheme == "ssh":
        alias = parsed.netloc
        path = parsed.path or "/"
        code, out = run(["ssh", alias, f"test -e {path!r} && echo exists || echo missing; hostname; whoami"])
        return code == 0 and "exists" in out.splitlines()[:1], out
    if parsed.scheme == "docker":
        alias = parsed.netloc
        rest = parsed.path.lstrip("/")
        container, _, container_path = rest.partition("/")
        if not container:
            return False, "docker uri must be docker://ssh-alias/container/path"
        cmd = f"docker inspect {container!r} >/dev/null && docker exec {container!r} test -e {'/' + container_path!r} && echo exists || echo missing"
        code, out = run(["ssh", alias, cmd])
        return code == 0 and "exists" in out.splitlines()[:1], out
    if parsed.scheme in {"compose", "vscode"}:
        return True, f"metadata-only check for {parsed.scheme}: {uri}"
    return False, f"unsupported uri scheme: {parsed.scheme}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check registered work locations.")
    parser.add_argument("--task-id", type=int)
    args = parser.parse_args()
    init_db()
    where = "WHERE task_id=?" if args.task_id else ""
    params = (args.task_id,) if args.task_id else ()
    ok_all = True
    with connect() as conn:
        rows = conn.execute(f"SELECT task_id, location_type, label, uri FROM task_work_locations {where} ORDER BY task_id, id", params).fetchall()
    if not rows:
        print("no registered locations")
        return 1
    for row in rows:
        ok, message = check_uri(row["uri"])
        ok_all = ok_all and ok
        status = "OK" if ok else "FAIL"
        label = row["label"] or row["location_type"]
        print(f"[{status}] task #{row['task_id']} {label}: {row['uri']}\n{message}\n")
    return 0 if ok_all else 2


if __name__ == "__main__":
    raise SystemExit(main())
