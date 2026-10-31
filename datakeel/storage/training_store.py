# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Persist named immutable version partitions and expose native guarded read projections."""

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.errors import ConflictError, NotFoundError, ValidationError
from datakeel.core.models import AssetRef, LineageEvent, utcnow
from datakeel.core.training_models import (
    LeakageReport,
    SplitComparison,
    SplitRequest,
    SplitSet,
    TrainingSample,
)
from datakeel.storage.annotation_frames import DISPLAY_FRAME
from datakeel.storage.database import Database
from datakeel.storage.events import append_event
from datakeel.storage.training_inputs import authorize_training, read_training_samples
from datakeel.storage.training_rows import TrainingSplitRow
from datakeel.storage.version_stream import require_version
from datakeel.training.leakage import leakage_report
from datakeel.training.splitting import distributions, split_samples

SPLIT_ALGORITHM_VERSION = "1.3-iterative-text"


def _build(
    dataset_id: str, version_id: str, request: SplitRequest, samples: tuple[TrainingSample, ...]
) -> SplitSet:
    members = split_samples(samples, request)
    policy = request.model_dump(mode="json")
    if request.stratification_source == "all":
        policy.pop("stratification_source")
    identity = json.dumps(
        [
            dataset_id,
            version_id,
            SPLIT_ALGORITHM_VERSION,
            policy,
            [member.model_dump(mode="json") for member in members],
        ],
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return SplitSet(
        id=hashlib.sha256(identity.encode()).hexdigest(),
        dataset_id=dataset_id,
        version_id=version_id,
        request=request,
        members=members,
        distributions=distributions(members),
        created_at=datetime(1970, 1, 1, tzinfo=UTC),
        algorithm_version=SPLIT_ALGORITHM_VERSION,
    )


def preview_split(
    db: Database,
    dataset_id: str,
    version_id: str,
    request: SplitRequest,
    *,
    access: AccessContext | None = None,
) -> SplitSet:
    """Compute a stable read-only partition without creating rows or lineage events."""
    with db.session() as session:
        samples = read_training_samples(
            session, dataset_id, version_id, request.group_field, access=access
        )
        return _build(dataset_id, version_id, request, samples)


def create_split(
    db: Database,
    dataset_id: str,
    version_id: str,
    request: SplitRequest,
    *,
    access: AccessContext | None = None,
) -> SplitSet:
    """Atomically freeze policy, content signals and annotations; identical retries reuse rows."""
    with db.session() as session:
        db.lock_writes(session)
        require_version(session, dataset_id, version_id, lock=True)
        authorize_training(session, dataset_id, version_id, access)
        previous = session.scalar(
            select(TrainingSplitRow).where(
                TrainingSplitRow.version_id == version_id, TrainingSplitRow.name == request.name
            )
        )
        if previous is not None:
            existing = read_split(session, dataset_id, previous.id, access=access)
            if existing.request != request:
                message = "Split name already belongs to a different immutable policy"
                raise ConflictError(message)
            return existing
        samples = read_training_samples(
            session, dataset_id, version_id, request.group_field, access=access
        )
        split = _build(dataset_id, version_id, request, samples).model_copy(
            update={"created_at": utcnow()}
        )
        session.add(
            TrainingSplitRow(
                id=split.id,
                dataset_id=dataset_id,
                version_id=version_id,
                name=request.name,
                created_at=split.created_at.timestamp(),
                payload=split.model_dump(mode="json"),
                samples=[sample.model_dump(mode="json") for sample in samples],
                coordinate_frame=DISPLAY_FRAME,
            )
        )
        append_event(
            session,
            LineageEvent(
                idempotency_key=f"training.split:{split.id}",
                operator="training.split",
                inputs=[AssetRef(asset_id=dataset_id, version=version_id)],
                outputs=[
                    AssetRef(asset_type="training_split", asset_id=split.id, version=version_id)
                ],
                source_module="training",
                params=request.model_dump(mode="json"),
                quality={"sample_count": len(split.members)},
            ),
        )
        session.commit()
        return split


def read_split(
    session: Session, dataset_id: str, split_id: str, *, access: AccessContext | None = None
) -> SplitSet:
    """Read one partition inside a caller-owned transaction with current native grants."""
    row = session.get(TrainingSplitRow, split_id)
    if row is None or row.dataset_id != dataset_id:
        message = "Training split was not found in this dataset"
        raise NotFoundError(message)
    split = SplitSet.model_validate(row.payload)
    authorize_training(
        session,
        dataset_id,
        row.version_id,
        access,
        tuple(member.sample_id for member in split.members),
    )
    return split


def get_split(
    db: Database, dataset_id: str, split_id: str, *, access: AccessContext | None = None
) -> SplitSet:
    """Read one immutable split with no content paths in the returned model."""
    with db.session() as session:
        return read_split(session, dataset_id, split_id, access=access)


def list_splits(
    db: Database, dataset_id: str, version_id: str, *, access: AccessContext | None = None
) -> tuple[SplitSet, ...]:
    """List exact-version split snapshots in creation order with stable identity ties."""
    with db.session() as session:
        require_version(session, dataset_id, version_id)
        authorize_training(session, dataset_id, version_id, access)
        rows = session.scalars(
            select(TrainingSplitRow)
            .where(
                TrainingSplitRow.dataset_id == dataset_id, TrainingSplitRow.version_id == version_id
            )
            .order_by(TrainingSplitRow.created_at, TrainingSplitRow.id)
        )
        return tuple(read_split(session, dataset_id, row.id, access=access) for row in rows)


def check_leakage(
    db: Database, dataset_id: str, split_id: str, *, access: AccessContext | None = None
) -> LeakageReport:
    """Compare frozen source signals rather than newer mutable annotation history."""
    with db.session() as session:
        split = read_split(session, dataset_id, split_id, access=access)
        row = session.get(TrainingSplitRow, split_id)
        if row is None:
            message = "Training split disappeared during leakage read"
            raise NotFoundError(message)
        samples = tuple(TrainingSample.model_validate(sample) for sample in row.samples)
        return leakage_report(samples, split)


def preview_leakage(
    db: Database,
    dataset_id: str,
    version_id: str,
    request: SplitRequest,
    *,
    access: AccessContext | None = None,
) -> LeakageReport:
    """Check an external directory partition or generated preview without writing facts."""
    with db.session() as session:
        samples = read_training_samples(
            session, dataset_id, version_id, request.group_field, access=access
        )
        return leakage_report(samples, _build(dataset_id, version_id, request, samples))


def compare_splits(
    db: Database,
    dataset_id: str,
    left_id: str,
    right_id: str,
    *,
    access: AccessContext | None = None,
) -> SplitComparison:
    """Compare membership changes only within one exact dataset version."""
    with db.session() as session:
        left = read_split(session, dataset_id, left_id, access=access)
        right = read_split(session, dataset_id, right_id, access=access)
        if left.version_id != right.version_id:
            message = "Training split comparison requires the same source version"
            raise ValidationError(message)
        assignments = {member.sample_id: member.split for member in left.members}
        return SplitComparison(
            left_id=left_id,
            right_id=right_id,
            changed_sample_ids=tuple(
                member.sample_id
                for member in right.members
                if assignments.get(member.sample_id) != member.split
            ),
            left=left.distributions,
            right=right.distributions,
        )
