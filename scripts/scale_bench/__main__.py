# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run one capacity workload and write its measurement envelope outside the source tree."""

import argparse
import cProfile
import hashlib
import importlib
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

from pydantic import JsonValue
from rich.console import Console
from sqlalchemy import text

from datakeel.core.models import utcnow
from scripts.scale_bench.common import check_resources, check_space
from scripts.scale_bench.isolation import isolated
from scripts.scale_bench.models import Config, ScenarioResult

MODULES = {
    "B1": "datasets",
    "B2": "pipeline",
    "B3": "catalog",
    "B4": "metrics",
    "B5": "api",
    "B6": "worker",
    "B7": "graph",
    "B8": "production_team",
}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=MODULES)
    parser.add_argument("--size", choices=("S", "M", "L"), default="S")
    parser.add_argument("--stack", choices=("sqlite", "postgres"), default="sqlite")
    parser.add_argument("--seed", type=int, default=23)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--think-ms", type=int, default=1000, help="B8 mean pause per step")
    parser.add_argument("--duration-seconds", type=float, help="B8 run length override")
    parser.add_argument("--virtual-users", type=int, help="B8 annotator count override")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path)
    return parser.parse_args()


def _system_value(name: str) -> str:
    if sys.platform != "darwin":
        return "unavailable"
    result = subprocess.run(  # noqa: S603  # Fixed sysctl metadata names below.
        ["/usr/sbin/sysctl", "-n", name], text=True, capture_output=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unavailable (restricted host)"


def _source_fingerprint() -> str:
    repository = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for directory in ("datakeel", "scripts"):
        for path in sorted((repository / directory).rglob("*.py")):
            digest.update(path.relative_to(repository).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _machine() -> dict[str, JsonValue]:
    return {
        "os": platform.platform(),
        "architecture": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "processor": _system_value("machdep.cpu.brand_string"),
        "memory_bytes": _system_value("hw.memsize"),
        "measurement_clock": "perf_counter",
    }


def _external(path: Path) -> Path:
    path = path.resolve()
    repository = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repository):
        message = "Raw measurements and profiles must be written outside the source tree"
        raise ValueError(message)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _revision() -> str:
    return subprocess.check_output(  # noqa: S603  # Fixed git metadata query.
        [shutil.which("git") or "/usr/bin/git", "rev-parse", "HEAD"],
        text=True,
        cwd=Path(__file__).resolve().parents[2],
    ).strip()  # Git is a development prerequisite.


def _execute(
    config: Config, envelope: dict[str, JsonValue], profiler: cProfile.Profile | None
) -> None:
    with isolated(config) as context:
        envelope["scale"] = context.scale.model_dump(mode="json")
        with context.db.session() as session:
            envelope["database_version"] = str(
                session.scalar(
                    text("SELECT sqlite_version()" if context.db.sqlite else "SELECT version()")
                )
            )
        module = importlib.import_module(f"scripts.scale_bench.{MODULES[config.scenario]}")
        if profiler:
            profiler.enable()
        result = ScenarioResult.model_validate(module.run(context))
        if profiler:
            profiler.disable()
        envelope["fixture_bytes_after"] = check_resources(context)
        envelope["result"] = result.model_dump(mode="json")
    envelope["cleanup"] = "owned temporary directory and schema removed"
    envelope["status"] = "ok"


def main() -> None:
    """Persist success or failure without recording connection URLs or secret settings."""
    args = _arguments()
    output = _external(args.output)
    profile = _external(args.profile) if args.profile else None
    config = Config.model_validate({key: getattr(args, key) for key in Config.model_fields})
    started = time.perf_counter()
    envelope: dict[str, JsonValue] = {
        "schema_version": 1,
        "started_at": utcnow().isoformat(),
        "machine": _machine(),
        "commit": _revision(),
        "version": version("datakeel"),
        "config": config.model_dump(mode="json"),
        "status": "failed",
        "source_sha256": _source_fingerprint(),
        "profile_enabled": bool(profile),
        "cleanup": "not started or failed",
    }
    profiler = cProfile.Profile() if profile else None
    try:
        envelope["free_bytes_before"] = check_space(output.parent)
        _execute(config, envelope, profiler)
    except Exception as exc:
        envelope["error_type"] = type(exc).__name__
        raise
    finally:
        if profiler and profile:
            profiler.disable()
            profiler.dump_stats(str(profile))
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        envelope.update(
            {
                "elapsed_seconds": time.perf_counter() - started,
                "peak_process_rss_bytes": peak if sys.platform == "darwin" else peak * 1024,
                "finished_at": utcnow().isoformat(),
            }
        )
        output.write_text(json.dumps(envelope, indent=2) + "\n")
        Console().print(f"{config.scenario} {config.size} {config.stack}: {envelope['status']}")
        Console().print(str(output))


if __name__ == "__main__":
    main()
