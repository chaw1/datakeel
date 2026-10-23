# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate four fictional enterprise SQLite sources and independent gold answers."""

import argparse
from pathlib import Path
from time import perf_counter

from rich.console import Console

from datakeel.sample_enterprise import generate_enterprise


def main() -> None:
    """Write the enterprise fixture to a local output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "generated")
    args = parser.parse_args()
    started = perf_counter()
    sample = generate_enterprise(args.output)
    Console().print(
        f"Generated {len(sample.sources)} sources, {sample.row_count} rows, "
        f"20 tables, 4 views and gold.json in {args.output} "
        f"in {perf_counter() - started:.3f}s"
    )


if __name__ == "__main__":
    main()
