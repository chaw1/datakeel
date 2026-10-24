# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load independent evaluation labels and original unfiltered recording outputs."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from datakeel.core.errors import ValidationError
from datakeel.core.kg_eval_models import KGCaseSuite, ScoredRecord
from datakeel.core.kg_models import Recording
from datakeel.kg.loader import contracts_path, load_contract

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import KGSchema
    from datakeel.core.kg_eval_models import KGCase


def load_cases(schema: KGSchema, path: Path | None = None) -> tuple[KGCaseSuite, str]:
    """Validate references against the chosen schema while preserving every source character."""
    path = path or contracts_path() / "eval" / "cases.yaml"
    suite = load_contract(path, KGCaseSuite)
    if len({case.id for case in suite.cases}) != len(suite.cases):
        msg = f"{path.name}:cases.id: duplicate case identity"
        raise ValidationError(msg)
    for index, case in enumerate(suite.cases):
        _validate_case(case, schema, f"{path.name}:cases.{index}")
    return suite, hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_case(case: KGCase, schema: KGSchema, location: str) -> None:
    types = {entity.name for entity in schema.entity_types}
    relations = {relation.name: relation for relation in schema.relations}
    names = {entity.name: entity.type for entity in case.entities}
    if len(names) != len(case.entities):
        msg = f"{location}.entities.name: duplicate canonical entity name"
        raise ValidationError(msg)
    if set(names.values()) - types:
        msg = f"{location}.entities.type: unknown entity type"
        raise ValidationError(msg)
    for field in ("relations", "optional", "traps"):
        for index, relation in enumerate(getattr(case, field)):
            prefix = f"{location}.{field}.{index}"
            if relation.relation not in relations:
                msg = f"{prefix}.relation: unknown relation type"
                raise ValidationError(msg)
            if relation.head not in names or relation.tail not in names:
                msg = f"{prefix}: undeclared gold endpoint"
                raise ValidationError(msg)
            definition = relations[relation.relation]
            if (
                names[relation.head] not in definition.domain
                or names[relation.tail] not in definition.range
            ):
                msg = f"{prefix}: endpoint type violates domain/range"
                raise ValidationError(msg)


def load_recording(path: Path) -> Recording:
    """Read replay provenance and records through the same validated product boundary."""
    return load_contract(path, Recording)


def original_records(recording: Recording, suite: KGCaseSuite) -> tuple[ScoredRecord, ...]:
    """Join by exact source bytes, never by a passage ID supplied in an external case file."""
    records = {record.text_hash: record for record in recording.records}
    result: list[ScoredRecord] = []
    for case in suite.cases:
        key = hashlib.sha256(case.text.encode("utf-8")).hexdigest()
        record = records.get(key)
        if record is None or record.original is None:
            result.append(ScoredRecord(pid=case.id, error="replay_not_found", failed_blocks=1))
        else:
            original = ScoredRecord.model_validate(record.original)
            result.append(original.model_copy(update={"pid": case.id}))
    return tuple(result)
