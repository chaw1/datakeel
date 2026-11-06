# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Invalidate relative coverage on any change in the frozen dynamic reference closure."""

from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError
from datakeel.core.evidence_models import Assertion
from datakeel.core.vector_measurements import CoverageMeasurement
from datakeel.core.vector_models import VectorError
from datakeel.dataset_store.rows import EventRow
from datakeel.pipeline.models import Node, Pipeline


def vector_assertion_current(session: Session, assertion: Assertion) -> bool:
    """Retain stale facts as audit history while refusing query/review use of changed R."""
    from datakeel.storage.vector_references import resolve_references  # noqa: PLC0415  # Break projection read cycle.

    if not isinstance(assertion.measurement, CoverageMeasurement):
        return True
    event = session.get(EventRow, assertion.producer_event_id)
    if event is None:
        return False
    node = Node(
        id="reference",
        operator="evidence.coverage_gap",
        inputs={"files": "$input.files"},
        params=event.payload["params"]["parameters"],
    )
    try:
        current = resolve_references(session, Pipeline(nodes=[node], outputs=["reference.files"]))[
            0
        ]
    except (VectorError, NotFoundError):
        return False
    return current.members == assertion.measurement.references
