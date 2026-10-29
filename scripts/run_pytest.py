# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run the full pytest gate with bounded, environment-controlled concurrency."""

import sys

import pytest

from scripts.test_workers import test_worker_count


def main() -> None:
    """Keep each test file together and merge worker coverage through pytest-cov."""
    workers = test_worker_count()
    raise SystemExit(
        pytest.main([*sys.argv[1:], "-n", str(workers if workers > 1 else 0), "--dist=loadfile"])
    )


if __name__ == "__main__":
    main()
