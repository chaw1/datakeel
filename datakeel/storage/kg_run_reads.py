# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""List extraction run reports only for source versions the caller may read."""

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import AuthorizationError
from datakeel.core.kg_execution import KGRun
from datakeel.core.models import AssetRef
from datakeel.storage.data_asset_access import require_access
from datakeel.storage.data_asset_reads import authorize_query
from datakeel.storage.database import Database
from datakeel.storage.kg_store import list_runs


def list_readable_runs(
    db: Database,
    dataset_id: str | None = None,
    version_id: str | None = None,
    limit: int = 100,
    *,
    access: AccessContext | None = None,
) -> tuple[KGRun, ...]:
    """Hide reports of protected sources: their proposal samples quote extracted text."""
    runs = list_runs(db, dataset_id, version_id, limit)
    caller = (access or AccessContext(actor="local-user", entry="ask", scope="query")).model_copy(
        update={"scope": "query"}
    )
    readable: list[AssetRef] = []
    for source in sorted({(run.dataset_id, run.version_id) for run in runs}):
        ref = AssetRef(asset_id=source[0], version=source[1])
        try:
            require_access(db, (ref,), caller, record=False)
        except AuthorizationError:
            continue
        readable.append(ref)
    authorize_query(db, tuple(readable), caller)
    allowed = {(ref.asset_id, ref.version) for ref in readable}
    return tuple(run for run in runs if (run.dataset_id, run.version_id) in allowed)
