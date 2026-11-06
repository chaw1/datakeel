# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reference-only cluster semantics and complete relative-coverage source closure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.models import AssetRef
from datakeel.core.vector_measurements import (
    ClusterMeasurement,
    CoverageMeasurement,
    OutlierMeasurement,
)
from datakeel.core.vector_models import vector_hash

if TYPE_CHECKING:
    from datakeel.core.evidence_models import Assertion


def assertion_references(assertion: Assertion) -> tuple[AssetRef, ...]:
    """Resolve all genuine sources, excluding a derived reference-only cluster endpoint."""
    refs = [assertion.subject, *(a.asset_ref for a in assertion.anchors)]
    if isinstance(assertion.object, AssetRef) and assertion.object.asset_type != "semantic_cluster":
        refs.append(assertion.object)
    if isinstance(assertion.measurement, CoverageMeasurement):
        refs.extend(m.subject for m in assertion.measurement.references)
    if isinstance(assertion.measurement, ClusterMeasurement):
        refs.extend(assertion.measurement.members)
    return tuple(dict.fromkeys(refs))


def validate_set_assertion(assertion: Assertion) -> None:
    """Enforce typed set measurements and the immutable source anchors they describe."""
    measurement = assertion.measurement
    anchors = tuple(a.asset_ref for a in assertion.anchors)
    valid = True
    if assertion.predicate == "semantic_cluster_member":
        valid = isinstance(measurement, ClusterMeasurement) and isinstance(
            assertion.object, AssetRef
        )
        if isinstance(measurement, ClusterMeasurement) and isinstance(assertion.object, AssetRef):
            members = measurement.members
            valid = (
                assertion.subject in members
                and tuple(sorted(members, key=lambda r: r.asset_id)) == members
                and len(set(members)) == len(members)
                and anchors == (assertion.subject,)
                and assertion.object.asset_id
                == vector_hash([members[0].asset_id, measurement.config_hash])
                and assertion.object.version == measurement.config_hash
            )
    elif assertion.predicate == "semantic_outlier":
        valid = isinstance(measurement, OutlierMeasurement) and anchors == (assertion.subject,)
    elif assertion.predicate == "coverage_gap":
        valid = isinstance(measurement, CoverageMeasurement)
        if isinstance(measurement, CoverageMeasurement):
            refs = tuple(m.subject for m in measurement.references)
            valid = (
                assertion.object == measurement.nearest
                and measurement.nearest in refs
                and assertion.subject not in refs
                and measurement.similarity < measurement.threshold
                and anchors == (assertion.subject, measurement.nearest)
                and measurement.reference_digest
                == vector_hash([m.model_dump(mode="json") for m in measurement.references])
            )
    if assertion.predicate in {"semantic_cluster_member", "semantic_outlier", "coverage_gap"}:
        valid = valid and all(a.selector.type == "whole" for a in assertion.anchors)
    if not valid:
        msg = "Invalid typed vector candidate or source closure"
        raise ValueError(msg)
