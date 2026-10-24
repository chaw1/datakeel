# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise automatic linking, versioned identity and durable human decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.evidence_models import AssertionDecisionRequest
from datakeel.core.models import AssetRef
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.events import all_events
from datakeel.storage.evidence_decisions import decide_assertions, list_decisions
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.link_queries import entity_links, list_links, read_link_context
from datakeel.storage.link_store import relink
from tests.storage.link_helpers import seed_link_graph, table_snapshot

if TYPE_CHECKING:
    from datakeel.core.evidence_models import AssertionStatus
    from datakeel.storage.database import Database


def _decide(db: Database, assertion_id: str, status: AssertionStatus) -> None:
    decide_assertions(
        db,
        AssertionDecisionRequest(
            assertion_ids=(assertion_id,),
            status=status,
            actor="reviewer",
            idempotency_key=f"{assertion_id}:{status}",
        ),
    )


def test_graph_before_catalog_links_automatically_and_refresh_is_idempotent(db: Database) -> None:
    """Late catalog import creates the association; identical refresh adds no event."""
    seed_link_graph(db)
    assert relink(db).links == 0
    publish_snapshot(db, table_snapshot())
    links = list_links(db)
    assert len(links) == 1
    assert links[0].match_kind == "unique"
    assert links[0].target.asset_ref.version == "1"
    assert links[0].assertion.extractor.id == "evidence.kg_link"
    assert entity_links(db, links[0].entity.asset_ref.asset_id) == links
    assert list_links(db, dataset_id="absent") == ()
    assert list_links(db, status="rejected") == ()
    with db.session() as session:
        before = len(all_events(session))
    assert relink(db).created == 0
    publish_snapshot(db, table_snapshot())
    with db.session() as session:
        assert len(all_events(session)) == before


def test_reviews_survive_graph_and_catalog_versions_without_duplicate_claims(db: Database) -> None:
    """The latest graph has one inherited link even when both endpoint versions change."""
    seed_link_graph(db)
    publish_snapshot(db, table_snapshot())
    original = list_links(db)[0]
    _decide(db, original.assertion.id, "rejected")
    seed_link_graph(db, version="v2")
    publish_snapshot(db, table_snapshot("renamed sales"))
    current = list_links(db)[0]
    assert current.assertion.id != original.assertion.id
    assert current.assertion.status == "rejected"
    assert current.assertion.subject.version == "v2"
    assert isinstance(current.assertion.object, AssetRef)
    assert current.assertion.object.version == "2"
    assert len(read_link_context(db).entities) == 2
    assert {item.subject.version for item in read_link_context(db).assertions} == {"v2"}
    assert relink(db).created == 0
    assert list_links(db)[0].assertion.status == "rejected"
    assert any("across_versions" in item.reason for item in list_decisions(db))
    assert len([item for item in list_assertions(db) if item.predicate == "link.maps_to"]) == 1


def test_accepted_link_survives_renaming_and_restore_resumes_matching_policy(db: Database) -> None:
    """A direct acceptance remains authoritative until a human explicitly restores it."""
    seed_link_graph(db)
    publish_snapshot(db, table_snapshot())
    _decide(db, list_links(db)[0].assertion.id, "accepted")
    publish_snapshot(db, table_snapshot("renamed"))
    accepted = list_links(db)[0]
    assert accepted.assertion.status == "accepted"
    _decide(db, accepted.assertion.id, "candidate")
    assert relink(db).invalidated == 1
    assert list_links(db) == ()


def test_reappearing_catalog_reactivates_old_identity_and_retains_review(db: Database) -> None:
    """Removing and reimporting the identical target revives its original reviewed identity."""
    seed_link_graph(db)
    snapshot = table_snapshot()
    publish_snapshot(db, snapshot)
    original = list_links(db)[0]
    _decide(db, original.assertion.id, "accepted")
    publish_snapshot(db, snapshot.model_copy(update={"objects": ()}))
    assert list_links(db) == ()
    publish_snapshot(db, snapshot)
    restored = list_links(db)[0]
    assert restored.assertion.id == original.assertion.id
    assert restored.assertion.status == "accepted"
    assert any(item.action == "reactivate" for item in list_decisions(db))


def test_cross_dataset_entities_remain_distinct_and_older_versions_do_not_retake_latest(
    db: Database,
) -> None:
    """Shared table matches merge no identities, and later old-version work stays historical."""
    seed_link_graph(db, version="v1")
    seed_link_graph(db, version="v2")
    seed_link_graph(db, name="sales", version="v1")
    seed_link_graph(db, dataset="other")
    publish_snapshot(db, table_snapshot())
    assert len(list_links(db)) == 2
    assert len(list_links(db, dataset_id="dataset")) == 1
    assert list_links(db, dataset_id="dataset")[0].entity.asset_ref.version == "v2"
    assert len(read_link_context(db).entities) == 4


def test_new_ambiguous_match_preserves_acceptance_and_later_unique_match_preserves_rejection(
    db: Database,
) -> None:
    """Catalog expansion or contraction changes matching strength without resetting reviews."""
    seed_link_graph(db)
    publish_snapshot(db, table_snapshot())
    original = list_links(db)[0]
    _decide(db, original.assertion.id, "accepted")
    additional = table_snapshot(scope="other")
    publish_snapshot(db, additional)
    links = list_links(db)
    assert len(links) == 2
    assert {link.match_kind for link in links} == {"ambiguous"}
    accepted = next(link for link in links if link.target.asset_ref.asset_id == "crm/main/sales")
    assert accepted.assertion.status == "accepted"
    rejected = next(link for link in links if link.target.asset_ref.asset_id == "other/main/sales")
    _decide(db, rejected.assertion.id, "rejected")
    publish_snapshot(db, table_snapshot().model_copy(update={"objects": ()}))
    remaining = list_links(db)
    assert len(remaining) == 1
    assert remaining[0].match_kind == "unique"
    assert remaining[0].assertion.status == "rejected"


def test_created_dataset_version_order_beats_graph_publication_order(db: Database) -> None:
    """Extracting the older dataset version later cannot replace a newer published graph."""
    with db.session() as session:
        session.add(DatasetRow(id="dataset", name="Generated version-order fixture"))
        session.flush()
        session.add_all(
            [
                VersionRow(id="v1", dataset_id="dataset", created_at=1, manifest=[]),
                VersionRow(id="v2", dataset_id="dataset", created_at=2, manifest=[]),
            ]
        )
        session.commit()
    seed_link_graph(db, version="v2")
    seed_link_graph(db, version="v1")
    publish_snapshot(db, table_snapshot())
    assert {link.entity.asset_ref.version for link in list_links(db)} == {"v2"}
