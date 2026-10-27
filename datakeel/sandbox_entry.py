# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standalone container supervisor; user imports happen in a separate child process."""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import cast


def main() -> None:
    """Keep tmpfs outputs alive until the host freezes and validates their archive."""
    status = Path("/status")
    log_limit = int(sys.argv[1])
    with (status / "stdout").open("wb") as stdout, (status / "stderr").open("wb") as stderr:
        result = subprocess.run(  # Fixed isolated interpreter and fixed script.
            [sys.executable, "-I", "/runner/worker.py", "/job", "/status"],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            check=False,
            env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
    reason = "completed" if result.returncode == 0 else "code_error"
    events = Path("/sys/fs/cgroup/memory.events")
    if events.is_file() and "oom_kill 0" not in events.read_text():
        reason = "memory_limit"
    for name in ("stdout", "stderr"):
        path = status / name
        if path.stat().st_size >= log_limit:
            reason = "log_limit"
        if path.stat().st_size > log_limit:
            with path.open("r+b") as stream:
                stream.truncate(log_limit)
    outputs: object = []
    result_path = status / "result.json"
    if reason == "completed" and result_path.exists():
        try:
            outputs = json.loads(result_path.read_text())
        except (ValueError, OSError):
            reason = "invalid_output"
    state = {"exit_code": result.returncode, "reason": reason, "outputs": outputs}
    (status / "status.json").write_text(json.dumps(cast("object", state), allow_nan=False))
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
