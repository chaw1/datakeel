# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Knowledge-free metric reads never materialize unrelated catalog inventories."""

import pytest
from sqlalchemy.orm import Session

from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.link_models import LinkGraph
from datakeel.storage import link_queries
from datakeel.storage.database import Database


@pytest.mark.parametrize("empty_graph", [False, True])
def test_empty_entity_context_does_not_read_catalog(
    db: Database, monkeypatch: pytest.MonkeyPatch, *, empty_graph: bool
) -> None:
    """Empty or document-only graph contexts cannot use catalog association targets."""

    def no_catalog(session: Session) -> CatalogSnapshot:
        msg = "Empty graph entity sets must not load catalog inventories"
        raise AssertionError(msg)

    def graphs(session: Session) -> tuple[LinkGraph, ...]:
        return (LinkGraph(dataset_id="fixture", version_id="v1"),) if empty_graph else ()

    monkeypatch.setattr(link_queries, "read_snapshot", no_catalog)
    monkeypatch.setattr(link_queries, "read_link_graphs", graphs)
    context = link_queries.read_link_context(db)
    assert not context.entities
    assert not context.links
