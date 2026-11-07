# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Owned isolated SQLite fixtures and typed readback; ORM rows stay inside this adapter."""

from pathlib import Path

from sqlalchemy import select

from datakeel.core.models import FileItem, LineageEvent
from datakeel.core.vector_measurements import ClusterMeasurement
from datakeel.core.vector_results import VectorCacheProduct, VectorSample
from datakeel.dataset_store.datasets import persist_files
from datakeel.dataset_store.rows import DatasetRow, EventRow, VersionRow
from datakeel.storage.database import Database
from datakeel.storage.evidence_store import validated_bundle
from datakeel.storage.vector_rows import VectorAttemptRow, VectorCacheRow
from scripts.we_e5.campaign_models import CacheSnapshot, Fixture
from scripts.we_e5.fixtures import Content, contents, references
from scripts.we_e5.models import RecordedFacts, Workload


def _files(directory: Path, values: tuple[Content, ...]) -> list[FileItem]:
    directory.mkdir(parents=True, exist_ok=True)
    files: list[FileItem] = []
    for value in values:
        path = directory / (value.asset_id + ".txt")
        path.write_text(value.text, encoding="utf-8")
        files.append(
            FileItem(id=value.asset_id, path=str(path), filename=path.name, modality="text")
        )
    return persist_files(files)


def create_fixture(db: Database, directory: Path, workload: Workload) -> Fixture:
    """Install deterministic generated source identities in a freshly initialized owned store."""
    targets = contents(workload)
    refs = references(workload)
    with db.session() as session:
        for name, values in (("targets", targets), ("references", refs)):
            files = _files(directory / name, values)
            manifest = [f.model_dump(mode="json") for f in files]
            session.add(
                DatasetRow(
                    id="we-e5-" + name,
                    name=name,
                    files=manifest,
                    created_at=workload.fixture_created_at,
                )
            )
            session.flush()
            session.add(
                VersionRow(
                    id="we-e5-" + name + "-v1",
                    dataset_id="we-e5-" + name,
                    created_at=workload.fixture_created_at,
                    manifest=manifest,
                )
            )
        session.commit()
    return Fixture(
        dataset_id="we-e5-targets",
        version_id="we-e5-targets-v1",
        reference_dataset_id="we-e5-references",
        target_ids=tuple(t.asset_id for t in targets),
        reference_ids=tuple(r.asset_id for r in refs),
    )


def new_version(db: Database, fixture: Fixture, path: Path) -> Fixture:
    """Change exactly one original asset, keeping every other source and all R unchanged."""
    with db.session() as session:
        original = session.get(VersionRow, fixture.version_id)
        if original is None:
            msg = "missing_owned_fixture_version"
            raise ValueError(msg)
        files = [FileItem.model_validate(item) for item in original.manifest]
        path.write_text("Synthetic E5 changed target only.", encoding="utf-8")
        changed = files[0].model_copy(update={"path": str(path)})
        files = [*persist_files([changed]), *files[1:]]
        version = "we-e5-targets-v2"
        session.add(
            VersionRow(
                id=version,
                created_at=original.created_at + 1,
                dataset_id=fixture.dataset_id,
                manifest=[file.model_dump(mode="json") for file in files],
            )
        )
        session.commit()
    return fixture.model_copy(update={"version_id": version})


def cache_snapshot(db: Database) -> CacheSnapshot:
    """Read the actual disposable caches, including their original peer identities."""
    with db.session() as session:
        products = [
            VectorCacheProduct.model_validate(row.payload)
            for row in session.scalars(select(VectorCacheRow))
        ]
    return CacheSnapshot(
        embeddings=tuple(
            sorted(
                (p.key, tuple(s.subject.asset_id for s in p.samples))
                for p in products
                if p.kind == "embedding"
            )
        ),
        globals=tuple(sorted(p.key for p in products if p.kind == "global")),
    )


def attempted_assets(db: Database, task_id: str) -> tuple[str, ...]:
    """Read durable attempts independently of in-memory transport counters."""
    with db.session() as session:
        return tuple(
            session.scalars(
                select(VectorAttemptRow.asset_id)
                .where(VectorAttemptRow.task_id == task_id)
                .order_by(VectorAttemptRow.asset_id)
            )
        )


def recorded_samples(db: Database, task_id: str) -> tuple[VectorSample, ...]:
    """Read actual committed fake model output from the embedding lineage bundle."""
    with db.session() as session:
        rows = session.scalars(
            select(EventRow).where(
                EventRow.payload["source_ref"].as_string() == task_id,
                EventRow.payload["operator"].as_string() == "evidence.vector_embed",
                EventRow.payload["event_type"].as_string() == "COMPLETE",
            )
        )
        events = tuple(LineageEvent.model_validate(row.payload) for row in rows)
    if len(events) != 1:
        msg = "one_embedding_publication_required"
        raise ValueError(msg)
    return validated_bundle(events[0]).vector_samples


def recorded_facts(db: Database, task_id: str) -> RecordedFacts:
    """Read all four committed node bundles to compare FAISS with actual fake-worker facts."""
    with db.session() as session:
        events = tuple(
            LineageEvent.model_validate(row.payload)
            for row in session.scalars(
                select(EventRow).where(
                    EventRow.payload["source_ref"].as_string() == task_id,
                    EventRow.payload["event_type"].as_string() == "COMPLETE",
                )
            )
        )
    bundles = {e.operator: validated_bundle(e) for e in events if "knowledge_bundle" in e.params}
    pairs = bundles["evidence.semantic_duplicate"].vector_pairs
    cluster = bundles["evidence.semantic_cluster"].vector_findings
    noise = bundles["evidence.semantic_outlier"].vector_findings
    gaps = bundles["evidence.coverage_gap"].vector_findings
    return RecordedFacts(
        pairs=tuple((p.left, p.right) for p in pairs),
        clusters=tuple(
            sorted(
                {
                    tuple(m.asset_id for m in f.measurement.members)
                    for f in cluster
                    if isinstance(f.measurement, ClusterMeasurement)
                }
            )
        ),
        noise=tuple(f.subject for f in noise),
        gaps=tuple((f.subject, f.object.asset_id) for f in gaps if f.object is not None),
    )
