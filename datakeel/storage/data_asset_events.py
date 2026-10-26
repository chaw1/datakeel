# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Distinguish data dependencies from controlled metadata management receipts."""

from sqlalchemy.orm import Session

from datakeel.core.models import LineageEvent
from datakeel.storage.events import all_events

_METADATA_ACTIONS = frozenset(
    {
        "import_catalog",
        "restore_catalog",
        "update_metric",
        "rollback_metric",
        "update_term",
        "rollback_term",
        "create_data_asset",
        "update_data_asset",
        "publish_data_asset",
        "withdraw_data_asset",
        "decide_asset_application",
        "revoke_asset_grant",
    }
)


def data_dependency_events(session: Session) -> list[LineageEvent]:
    """Exclude snapshot receipts: their input/output lists do not imply data flow."""
    return [event for event in all_events(session) if event.operator not in _METADATA_ACTIONS]
