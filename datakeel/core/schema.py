# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable schema contracts and fail-closed validation, without domain imports."""

from typing import Protocol, cast, runtime_checkable

from pydantic import ConfigDict, Field
from sqlalchemy import Table, inspect
from sqlalchemy.engine import Connection
from sqlalchemy.orm import DeclarativeBase

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel


class Base(DeclarativeBase):
    """Share declarative metadata without loading any application schema."""


@runtime_checkable
class Installer(Protocol):
    """Accept the migration owner's connection without owning its transaction."""

    def __call__(self, connection: Connection, *, sqlite: bool) -> None:
        """Install fixed constraints for the selected dialect."""
        ...


class SchemaInstaller(BoundaryModel):
    """Name and order a fixed, explicitly bound installer."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    key: str
    order: int = Field(ge=0)
    install: Installer


class SchemaContribution(BoundaryModel):
    """Declare one owner's rows and installers without mutable registration."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)

    owner: str = Field(min_length=1)
    order: int = Field(ge=0)
    rows: tuple[type[Base], ...]
    installers: tuple[SchemaInstaller, ...] = ()


class TableOwner(BoundaryModel):
    """Bind one canonical table to its independent owner."""

    table: str
    owner: str


class InstallerRequirement(BoundaryModel):
    """Keep the expected installer identity, owner and order independent of wiring."""

    key: str
    owner: str
    order: int


class CanonicalSchema(BoundaryModel):
    """Carry an independently frozen table-owner and installer oracle."""

    tables: tuple[TableOwner, ...]
    installers: tuple[InstallerRequirement, ...]
    owners: tuple[str, ...]


def _reject(*, condition: bool, message: str) -> None:
    if condition:
        raise ValidationError(message)


def validate_tables(actual: frozenset[str], canonical: CanonicalSchema) -> None:
    """Reject missing or unexpected live tables, including empty databases."""
    expected = frozenset(item.table for item in canonical.tables)
    _reject(
        condition=actual != expected,
        message=f"Canonical tables mismatch: {sorted(actual ^ expected)}",
    )


def validate_migration_source(
    connection: Connection, *, sqlite: bool, canonical: CanonicalSchema
) -> None:
    """Reject nonempty SQLite and partial or unexpected PostgreSQL schema before DDL."""
    tables = frozenset(inspect(connection).get_table_names())
    if inspect(connection).get_view_names() or (sqlite and tables):
        msg = "Explicit schema initializer requires an empty database"
        raise ValidationError(msg)
    if tables:
        validate_tables(tables, canonical)


def validate_contributions(
    contributions: tuple[SchemaContribution, ...], canonical: CanonicalSchema
) -> None:
    """Check proposed rows and installers before taking a connection or writing DDL."""
    owners = tuple(item.owner for item in contributions)
    _reject(
        condition=owners != canonical.owners,
        message="Missing, duplicate or unordered schema owners",
    )
    _reject(
        condition=tuple(item.order for item in contributions) != tuple(range(len(contributions))),
        message="Duplicate or ambiguous contribution order",
    )
    tables = tuple(
        TableOwner(table=_row_table(row).name, owner=item.owner)
        for item in contributions
        for row in item.rows
    )
    _reject(
        condition=len({item.table for item in tables}) != len(tables),
        message="Duplicate schema table",
    )
    _reject(
        condition=sorted(tables, key=lambda item: item.table)
        != sorted(canonical.tables, key=lambda item: item.table),
        message="Proposed tables or owners differ from canonical schema",
    )
    validate_tables(frozenset(Base.metadata.tables), canonical)
    _validate_installers(contributions, canonical)


def _validate_installers(
    contributions: tuple[SchemaContribution, ...], canonical: CanonicalSchema
) -> None:
    actual = tuple(
        InstallerRequirement(key=installer.key, order=installer.order, owner=item.owner)
        for item in contributions
        for installer in item.installers
    )
    _reject(
        condition=len({item.key for item in actual}) != len(actual)
        or len({item.order for item in actual}) != len(actual),
        message="Duplicate schema installer or order",
    )
    _reject(
        condition=tuple(sorted(actual, key=lambda item: item.order)) != canonical.installers,
        message="Missing, unexpected or unordered schema installer",
    )
    _reject(
        condition=any(
            tuple(sorted(item.installers, key=lambda i: i.order)) != item.installers
            for item in contributions
        ),
        message="Unordered contribution installers",
    )


def _row_table(row: type[Base]) -> Table:
    table = row.__table__
    _reject(
        condition=not isinstance(table, Table) or row.metadata is not Base.metadata,
        message="Schema rows must share the migration metadata",
    )
    if not isinstance(table, Table):
        msg = "Schema row must map a table"
        raise ValidationError(msg)
    return cast("Table", table)
