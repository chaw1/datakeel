# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preview, save and inspect reproducible training splits from local version facts."""

import argparse
import json

from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import JsonDocument
from datakeel.core.training_models import SplitRatios, SplitRequest
from datakeel.ontology.training_functions import invoke_training
from datakeel.ontology.training_parameters import TrainingDistributionParams, TrainingLeakageParams
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import list_versions
from datakeel.storage.training_store import compare_splits, create_split, list_splits


def register_parser(commands: CommandGroup) -> None:
    """Add training reads and explicit named split creation without changing export policy."""
    group = commands.add_parser("training")
    subcommands = group.add_subparsers(dest="training_command", required=True)
    for name in ("distribution", "leakage", "create", "list", "compare"):
        sub = subcommands.add_parser(name)
        sub.add_argument("dataset")
        sub.add_argument("--version")
        sub.add_argument("--json", action="store_true", dest="json_output")
        if name == "compare":
            sub.add_argument("left")
            sub.add_argument("right")
        elif name != "list":
            _split_arguments(sub, name)


def _split_arguments(parser: argparse.ArgumentParser, command: str) -> None:
    parser.add_argument("--split-set")
    parser.add_argument("--name", required=command == "create", default="preview")
    parser.add_argument("--train", type=float, default=0.8)
    parser.add_argument("--val", type=float, default=0.1)
    parser.add_argument("--test", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--group-field")
    parser.add_argument("--no-stratify", action="store_true")
    parser.add_argument("--directory", action="store_true", default=command == "leakage")
    parser.add_argument("--image-threshold", type=int, default=8)
    parser.add_argument("--text-threshold", type=int, default=3)


def _request(args: argparse.Namespace) -> SplitRequest:
    return SplitRequest(
        name=args.name,
        ratios=SplitRatios(train=args.train, val=args.val, test=args.test),
        seed=args.seed,
        stratify=not args.no_stratify,
        group_field=args.group_field,
        source="directory" if args.directory else "generated",
        image_threshold=args.image_threshold,
        text_threshold=args.text_threshold,
    )


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Use the same guarded typed services as the HTTP, Agent and MCP entry points."""
    access = AccessContext(actor="local-user", entry="agent", scope="query")
    if args.training_command in {"distribution", "leakage"}:
        model = (
            TrainingLeakageParams
            if args.training_command == "leakage"
            else TrainingDistributionParams
        )
        params = model(
            dataset_id=args.dataset,
            version_id=args.version,
            split_set_id=args.split_set,
            request=_request(args),
        )
        result = invoke_training(
            db,
            f"training_{args.training_command}",
            JsonDocument.model_validate(params.model_dump(mode="json")),
            access,
        )
        payload = result.data
    elif args.training_command == "compare":
        payload = compare_splits(db, args.dataset, args.left, args.right, access=access).model_dump(
            mode="json"
        )
    else:
        version = args.version or list_versions(db, args.dataset, access=access)[-1].id
        payload = (
            [item.model_dump(mode="json") for item in list_splits(db, args.dataset, version)]
            if args.training_command == "list"
            else create_split(db, args.dataset, version, _request(args), access=access).model_dump(
                mode="json"
            )
        )
    Console().print(
        json.dumps(payload, ensure_ascii=False, indent=2),
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
