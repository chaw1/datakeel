# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Register production tables and install immutable-history constraints in both stores."""

from sqlalchemy.engine import Connection

from datakeel.storage.identity_rows import RoleBindingRow, RoleRow, SkillRow, TeamRow, UserRow
from datakeel.storage.identity_sessions import REGISTERED_IDENTITY_RUNTIME_ROWS
from datakeel.storage.production_catalog_rows import (
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionPrelabelRunRow,
    ProductionTemplateRow,
    install_catalog_constraints,
)
from datakeel.storage.production_idempotency import ProductionPreparationRow
from datakeel.storage.production_rows import (
    ProductionAssignmentRow,
    ProductionMemberRow,
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionReviewRow,
    ProductionRevisionRow,
    ProductionSummaryRow,
    ProductionTaskRow,
    install_production_constraints,
)

REGISTERED_PRODUCTION_MODELS = (
    *REGISTERED_IDENTITY_RUNTIME_ROWS,
    UserRow,
    TeamRow,
    SkillRow,
    RoleRow,
    RoleBindingRow,
    ProductionLabelSetRow,
    ProductionModelRow,
    ProductionPrelabelRunRow,
    ProductionTemplateRow,
    ProductionPreparationRow,
    ProductionAssignmentRow,
    ProductionMemberRow,
    ProductionPackageRow,
    ProductionProjectRow,
    ProductionReviewRow,
    ProductionRevisionRow,
    ProductionSummaryRow,
    ProductionTaskRow,
)


def install_production_schema(connection: Connection, *, sqlite: bool) -> None:
    """Protect published vocabularies and append-only annotation and review history."""
    install_catalog_constraints(connection, sqlite=sqlite)
    install_production_constraints(connection, sqlite=sqlite)
