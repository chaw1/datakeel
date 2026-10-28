# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read record-level training findings from an uploaded dataset without changing it."""

import argparse

from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.training_governance import TrainingQualityQuery
from datakeel.storage.database import Database
from datakeel.storage.training_reads import read_training_quality


def register_parser(commands: CommandGroup) -> None:
    """Add a model-free, read-only training quality report command."""
    parser = commands.add_parser("training-quality")
    parser.add_argument("dataset_id")
    parser.add_argument("--version-id")


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print real rule observations as JSON without preparing or executing a mutation."""
    query = TrainingQualityQuery(dataset_id=args.dataset_id, version_id=args.version_id)
    report = read_training_quality(db, query)
    Console().print(report.model_dump_json(indent=2), markup=False, highlight=False, soft_wrap=True)
