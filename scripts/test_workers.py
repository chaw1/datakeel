# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Share the bounded local/CI concurrency policy between test executors."""

import os

MAX_DEFAULT_WORKERS = 16


def test_worker_count() -> int:
    """Read an explicit positive worker count, or use at most sixteen logical CPUs."""
    value = os.environ.get("DATAKEEL_TEST_WORKERS")
    if value is None:
        return max(1, min(MAX_DEFAULT_WORKERS, os.cpu_count() or 1))
    try:
        workers = int(value)
    except ValueError as error:
        msg = "DATAKEEL_TEST_WORKERS must be a positive integer"
        raise ValueError(msg) from error
    if workers < 1:
        msg = "DATAKEEL_TEST_WORKERS must be a positive integer"
        raise ValueError(msg)
    return workers
