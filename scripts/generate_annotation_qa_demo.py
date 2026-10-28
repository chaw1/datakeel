# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate fictional annotation panels, optionally importing a local SQLite demonstration."""

import argparse
from pathlib import Path

from rich.console import Console

from datakeel.harness.annotation_cases import seed_annotation_qa_demo
from datakeel.sample_annotation_qa import generate_annotation_qa_samples
from datakeel.storage.database import Database


def main() -> None:
    """Write fixtures without credentials or models; require an explicit SQLite import path."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--database", type=Path, help="Optional local SQLite database file")
    args = parser.parse_args()
    if args.database is None:
        samples = generate_annotation_qa_samples(args.output)
        Console().print(
            f"Generated {len(samples.paths)} samples, three reviewers, "
            "initial.json and reworked.json."
        )
        return
    args.database.parent.mkdir(parents=True, exist_ok=True)
    db = Database(f"sqlite:///{args.database.resolve()}")
    try:
        db.migrate()
        summary = seed_annotation_qa_demo(db, args.output)
        Console().print(summary.model_dump_json(indent=2), markup=False)
    finally:
        db.engine.dispose()


if __name__ == "__main__":
    main()
