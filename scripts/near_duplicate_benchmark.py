# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure isolated Python/Rust hash comparison without image decoding or external services."""

import argparse
import hashlib
import importlib.metadata
import os
import resource
import signal
import struct
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, sleep

from rich.console import Console

from datakeel.core.models import BoundaryModel
from datakeel.operators.evidence.near_duplicate_hashes import PYTHON_VERSION, compare_python
from scripts.near_duplicate_benchmark_data import (
    Machine,
    Measurement,
    Mode,
    generate_workload,
    machine_information,
)


class BenchmarkResults(BoundaryModel):
    """Keep the complete measured matrix and its reproducibility metadata together."""

    measured_at: datetime
    machine: Machine
    measurements: tuple[Measurement, ...]
    measurement_notes: tuple[str, ...] = ()
    source_results: tuple[str, ...] = ()
    recall_definition: str = "Fraction of independently planted direct pairs recovered."
    timing_definition: str = (
        "Completed cases: comparison call only, excluding generation/imports/startup; "
        "timeouts: observed subprocess wall seconds."
    )
    memory_definition: str = (
        "OS child-process high-water RSS, including imports, inputs and results."
    )


def measure(request: Measurement) -> Measurement:
    """Time the real comparator and score against ground truth withheld from that comparator."""
    workload = generate_workload(request.size, request.seed)
    comparison = compare_python
    if request.implementation == "rust":
        # Optional extension import belongs outside the measured comparison call.
        import datakeel_accel  # noqa: PLC0415  # Required only for the explicit Rust cases.

        comparison = datakeel_accel.compare
    started = perf_counter()
    pairs = comparison(workload.hashes, request.threshold, request.prefix_bits, request.mode)
    elapsed = perf_counter() - started
    found = len(set(workload.planted).intersection(pairs))
    digest = hashlib.sha256()
    for pair in pairs:
        digest.update(struct.pack("<QQB", *pair))
    version = (
        PYTHON_VERSION
        if request.implementation == "python"
        else importlib.metadata.version("datakeel-accel")
    )
    return request.model_copy(
        update={
            "elapsed_seconds": elapsed,
            "found_planted_pairs": found,
            "recall": found / len(workload.planted) if workload.planted else 1.0,
            "returned_pairs": len(pairs),
            "result_digest": digest.hexdigest(),
            "workload_digest": workload.digest,
            "implementation_version": version,
        }
    )


def _wait_for_child(pid: int, timeout: float) -> tuple[bool, int, resource.struct_rusage]:
    started = perf_counter()
    while True:
        finished, status, usage = os.wait4(pid, os.WNOHANG)
        if finished:
            return False, status, usage
        if perf_counter() - started >= timeout:
            os.kill(pid, signal.SIGKILL)
            _, status, usage = os.wait4(pid, 0)
            return True, status, usage
        sleep(0.05)


def run_case(request: Measurement, directory: Path) -> Measurement:
    """Launch one local-only POSIX process and retain its exact high-water RSS even on timeout."""
    name = f"{request.size}-{request.implementation}-{request.mode}"
    output, errors = directory / f"{name}.json", directory / f"{name}.stderr"
    command = [
        sys.executable,
        "-m",
        "scripts.near_duplicate_benchmark",
        "--worker-request",
        request.model_dump_json(),
        "--output",
        str(output),
    ]
    started = perf_counter()
    pid = os.posix_spawn(
        sys.executable,
        command,
        {"PATH": os.defpath, "PYTHONHASHSEED": "0"},
        file_actions=[
            (os.POSIX_SPAWN_OPEN, 2, str(errors), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        ],
    )
    timed_out, status, usage = _wait_for_child(pid, request.timeout_seconds)
    wall = perf_counter() - started
    peak = int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024))
    if timed_out:
        return request.model_copy(
            update={
                "status": "timeout",
                "elapsed_seconds": wall,
                "wall_seconds": wall,
                "peak_rss_bytes": peak,
            }
        )
    if os.waitstatus_to_exitcode(status) != 0:
        message = f"Benchmark child {name} failed: {errors.read_text()[-2000:]}"
        raise RuntimeError(message)
    result = Measurement.model_validate_json(output.read_bytes())
    return result.model_copy(update={"wall_seconds": wall, "peak_rss_bytes": peak})


def _validate_matrix(measurements: list[Measurement]) -> None:
    completed: dict[tuple[int, Mode], Measurement] = {}
    for result in measurements:
        if result.status != "completed":
            continue
        if result.mode == "exact" and result.recall != 1.0:
            message = "Exact comparison missed independently planted near-duplicate pairs"
            raise RuntimeError(message)
        key = (result.size, result.mode)
        previous = completed.get(key)
        if previous is not None and (
            previous.workload_digest != result.workload_digest
            or previous.result_digest != result.result_digest
        ):
            message = "Python and Rust benchmark results differ on the same generated workload"
            raise RuntimeError(message)
        completed[key] = result


def _run_matrix(args: argparse.Namespace) -> None:
    measurements: list[Measurement] = []
    with TemporaryDirectory(prefix="datakeel-hash-benchmark-") as temporary:
        directory = Path(temporary)
        for size in args.sizes:
            for mode in args.modes:
                for implementation in args.implementations:
                    request = Measurement(
                        size=size,
                        implementation=implementation,
                        mode=mode,
                        status="completed",
                        elapsed_seconds=0,
                        wall_seconds=0,
                        peak_rss_bytes=0,
                        timeout_seconds=args.timeout,
                        seed=args.seed,
                        planted_pairs=size // 100,
                    )
                    result = run_case(request, directory)
                    measurements.append(result)
                    report = BenchmarkResults(
                        measured_at=datetime.now(UTC),
                        machine=machine_information(),
                        measurements=tuple(measurements),
                    )
                    args.output.write_text(report.model_dump_json(indent=2) + "\n")
                    Console().print(result.model_dump_json(), markup=False)
                    _validate_matrix(measurements)


def main() -> None:
    """Run all four implementations/modes at 10k, 100k and 1m, with a 600-second case limit."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10_000, 100_000, 1_000_000])
    parser.add_argument("--seed", type=int, default=20261027)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument(
        "--modes", choices=["prefix", "exact"], nargs="+", default=["prefix", "exact"]
    )
    parser.add_argument(
        "--implementations", choices=["python", "rust"], nargs="+", default=["python", "rust"]
    )
    parser.add_argument("--worker-request", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_request:
        result = measure(Measurement.model_validate_json(args.worker_request))
        args.output.write_text(result.model_dump_json() + "\n")
    else:
        _run_matrix(args)


if __name__ == "__main__":
    main()
