# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Group-aware development splits and independent-party summary schemas only."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from scripts.we_e1.models import Asset, Boundary, Digest
from scripts.we_e1.preprocess import sha256
from scripts.we_e1.public_models import PublicAsset

SEED = "we-e1-development-v1"


def identities(asset: Asset | PublicAsset) -> frozenset[str]:
    """Connect shared source, original content, duplicate cluster and transform family."""
    return frozenset(
        (
            "source:" + asset.stable_source_id,
            "original:" + asset.original_sha256,
            "content:" + asset.content_sha256,
            "group:" + asset.original_group,
            "cluster:" + asset.near_duplicate_cluster,
            "family:" + asset.transformation_family,
        )
    )


def split_assets[DevelopmentAsset: (Asset, PublicAsset)](
    assets: tuple[DevelopmentAsset, ...],
) -> tuple[DevelopmentAsset, ...]:
    """Split connected identity components, independent of input order or variant count."""
    pending = {asset.asset_id: asset for asset in assets}
    if len(pending) != len(assets):
        msg = "duplicate asset ID"
        raise ValueError(msg)
    assigned: dict[str, DevelopmentAsset] = {}
    while pending:
        first = min(pending)
        component = [pending.pop(first)]
        keys = set(identities(component[0]))
        while True:
            linked = [key for key, asset in pending.items() if keys & identities(asset)]
            if not linked:
                break
            for key in sorted(linked):
                asset = pending.pop(key)
                component.append(asset)
                keys.update(identities(asset))
        # Stable group identities, rather than the number/order of transformed variants.
        root_keys = sorted(key for key in keys if not key.startswith("content:"))
        digest = sha256((SEED + "\n" + "\n".join(root_keys)).encode())
        split = "dev_tune" if int(digest, 16) % 2 == 0 else "dev_validation"
        assigned.update(
            {asset.asset_id: asset.model_copy(update={"split": split}) for asset in component}
        )
    return tuple(assigned[key] for key in sorted(assigned))


def split_overlap(assets: tuple[Asset, ...] | tuple[PublicAsset, ...]) -> tuple[str, ...]:
    """Return development-only identity intersections, without reading any other dataset."""
    tune = {key for a in assets if a.split == "dev_tune" for key in identities(a)}
    validation = {key for a in assets if a.split == "dev_validation" for key in identities(a)}
    return tuple(sorted(tune & validation))


class IndependentSummary(Boundary):
    """Allow only aggregate independent results; never accept held-out rows or paths."""

    contract_version: Literal["we-e1-v1"]
    development_evidence_sha256: Digest
    development_manifest_sha256: Digest
    spec_bundle_sha256: Digest
    auditor_session: str
    checked_dimensions: tuple[
        Literal[
            "stable_source",
            "original_content",
            "transformation_family",
            "semantic_group",
            "near_duplicate_cluster",
        ],
        ...,
    ]
    development_public_rows: Annotated[int, Field(gt=0)]
    holdout_rows: Annotated[int, Field(gt=0)]
    overlap_counts: Annotated[tuple[int, int, int, int, int], Field()]
    command_audit_complete: bool
    holdout_access_by_implementer: bool
    result: Literal["pass", "fail"]

    @model_validator(mode="after")
    def require_complete_check(self) -> IndependentSummary:
        """A passing result requires all five checks, no overlaps and a clean audit."""
        expected = (
            "stable_source",
            "original_content",
            "transformation_family",
            "semantic_group",
            "near_duplicate_cluster",
        )
        if self.checked_dimensions != expected:
            msg = "all intersection dimensions must be checked exactly once"
            raise ValueError(msg)
        if any(count < 0 for count in self.overlap_counts):
            msg = "negative intersection count"
            raise ValueError(msg)
        if self.result == "pass" and (
            any(self.overlap_counts)
            or not self.command_audit_complete
            or self.holdout_access_by_implementer
        ):
            msg = "passing isolation summary contradicts its evidence"
            raise ValueError(msg)
        return self
