# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find conservative key candidates using names and complete value inclusion."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from datakeel.operators.table.inference import is_identifier
from datakeel.operators.table.models import ForeignKeyCandidate, TableProfile

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.operators.table.io import TableData
    from datakeel.operators.table.params import ProfileParams


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _compatible(source: str, target: str, target_path: Path) -> bool:
    if (
        _name_key(source) == _name_key(target)
        and is_identifier(source)
        and source.casefold() not in {"id", "code", "uuid"}
    ):
        return True
    stem = _name_key(target_path.stem).removesuffix("s")
    source_key = _name_key(source)
    return target.casefold() == "id" and source_key in {stem + "id", stem + "code"}


def _values(data: TableData, column: int, params: ProfileParams) -> frozenset[str]:
    nulls = {value.strip().casefold() for value in params.null_values}
    return frozenset(
        value for row in data.rows if (value := row[column].strip()).casefold() not in nulls
    )


def foreign_key_candidates(
    source_index: int,
    paths: tuple[Path, ...],
    tables: tuple[TableData, ...],
    profiles: tuple[TableProfile, ...],
    params: ProfileParams,
) -> tuple[ForeignKeyCandidate, ...]:
    """Require an ID-like name, a unique target and complete nonnull value inclusion."""
    candidates: list[ForeignKeyCandidate] = []
    source = tables[source_index]
    for column_index, column in enumerate(source.columns):
        observed = _values(source, column_index, params)
        if not observed:
            continue
        for target_index, target in enumerate(tables):
            if target_index == source_index:
                continue
            for reference_index, reference in enumerate(profiles[target_index].columns):
                if not reference.primary_key_candidate or not _compatible(
                    column, reference.name, paths[target_index]
                ):
                    continue
                domain = _values(target, reference_index, params)
                if observed <= domain:
                    candidates.append(
                        ForeignKeyCandidate(
                            column=column,
                            referenced_file=paths[target_index].name,
                            referenced_column=reference.name,
                            matched_distinct_values=len(observed),
                            coverage=1.0,
                        )
                    )
    return tuple(candidates)
