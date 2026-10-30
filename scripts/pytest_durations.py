# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Refresh the per-module seconds that balance CI pytest shards from shard evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.pytest_shards import DURATIONS_PATH, OUTCOMES_FILE, ShardOutcomes, module_of

if TYPE_CHECKING:
    from collections.abc import Sequence


def module_durations(roots: Sequence[Path]) -> dict[str, float]:
    """Sum seconds per module in each outcome file and keep the slowest observation.

    Each stack reports every module once, so the maximum is the slower stack's time.
    """
    slowest: dict[str, float] = {}
    for root in roots:
        for path in sorted(root.rglob(OUTCOMES_FILE)):
            evidence = ShardOutcomes.model_validate_json(path.read_text(encoding="utf-8"))
            totals: Counter[str] = Counter()
            for node, seconds in evidence.durations.items():
                totals[module_of(node)] += seconds
            for module, seconds in totals.items():
                slowest[module] = max(slowest.get(module, 0.0), seconds)
    return {module: round(slowest[module], 2) for module in sorted(slowest)}


def main() -> None:
    """Write sorted module seconds from downloaded shard report directories."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, default=DURATIONS_PATH)
    args = parser.parse_args()
    durations = module_durations(args.reports)
    args.output.write_text(json.dumps(durations, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
