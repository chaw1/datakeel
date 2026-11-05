# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply only the separately inventoried fake-vector schema and adapter increment."""

import hashlib
from pathlib import Path

from datakeel.core.models import BoundaryModel

EXTENSION = Path("contracts/persistence/we-e2-extension.json")
VECTOR_CANONICAL = Path("datakeel/persistence/vector_tables.json")


class SchemaExtension(BoundaryModel):
    """Pin individual additions without replacing the pre-existing frozen baseline."""

    vector_canonical_sha256: str
    storage_additions: dict[str, int]
    storage_paths: tuple[str, ...]
    schema_additions: dict[str, int]
    import_exceptions: tuple[str, ...]
    legacy_row_imports: dict[str, dict[str, list[str]]]


def extension() -> SchemaExtension:
    """Read the explicit E2 increment independently from runtime contributions."""
    return SchemaExtension.model_validate_json(EXTENSION.read_bytes())


def allowances(increment: SchemaExtension) -> dict[str, int]:
    """Compute finite ratchet increments from the named paths and import edges only."""
    return {
        "storage_lines": sum(increment.storage_additions.values()),
        "storage_files": len(increment.storage_paths),
        "import_exceptions": len(increment.import_exceptions),
        "storage_exceptions": sum(
            "datakeel.storage" in edge for edge in increment.import_exceptions
        ),
    }


def canonical_violations(increment: SchemaExtension) -> list[str]:
    """Fail closed if the separate vector owner oracle drifts."""
    if (
        hashlib.sha256(VECTOR_CANONICAL.read_bytes()).hexdigest()
        != increment.vector_canonical_sha256
    ):
        return ["Frozen vector table-owner artifact changed"]
    return []
