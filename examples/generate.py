# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Regenerate paired evidence inputs and their independent evaluation gold."""

import argparse
from pathlib import Path
from time import perf_counter

from rich.console import Console

from datakeel.sample_evidence import generate_samples


def main() -> None:
    """Generate the requested sample count under a reproducible output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "sample-data")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be a positive integer")
    started = perf_counter()
    gold = generate_samples(args.output, args.samples)
    elapsed = perf_counter() - started
    Console().print(
        f"Generated {gold.sample_count} samples ({gold.train_count} train, {gold.val_count} val) "
        f"and gold.json in {args.output} in {elapsed:.3f}s"
    )


if __name__ == "__main__":
    main()
