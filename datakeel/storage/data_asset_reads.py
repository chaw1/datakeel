# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply one native query policy without duplicating outer tool usage records."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import AssetRef
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.database import Database


def authorize_query(db: Database, refs: tuple[AssetRef, ...], access: AccessContext | None) -> None:
    """Authorize direct evidence reads and leave Agent/MCP auditing to the outer boundary."""
    caller = (access or AccessContext(actor="local-user", entry="ask", scope="query")).model_copy(
        update={"scope": "query"}
    )
    require_access(db, refs, caller, record=caller.entry not in {"agent", "mcp"})
