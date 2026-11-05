# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen public-development artifacts; upstream content remains external data."""

from typing import Literal

from scripts.we_e1.models import Boundary, Digest, EvidenceFile


class LicenseRecord(Boundary):
    """Separate a dataset card's silence from underlying content licensing."""

    stable_id: str
    license_id: str
    license_url: str | None
    dataset_card_license: Literal["not_declared_More_Information_Needed"] | None
    basis: str
    attribution: str
    obligations: tuple[str, ...]
    modifications: tuple[str, ...]
    evidence: tuple[EvidenceFile, ...]
    eligible: bool
    limitations: tuple[str, ...]
    independent_license_review: Literal["pending"] = "pending"


class LicenseLedger(Boundary):
    """Bind per-original license decisions to retained raw evidence."""

    contract_version: Literal["we-e1-v1"] = "we-e1-v1"
    records: tuple[LicenseRecord, ...]


class PublicAsset(Boundary):
    """Reference retained bytes without putting large originals in the public tree."""

    asset_id: str
    modality: Literal["text", "image"]
    source_kind: Literal["real_public_development"] = "real_public_development"
    stable_source_id: str
    original_group: str
    near_duplicate_cluster: str
    transformation_family: str
    variant: str
    original_sha256: Digest
    content_sha256: Digest
    content: EvidenceFile
    split: Literal["dev_tune", "dev_validation"] = "dev_tune"
    license_eligible: bool


class PublicManifest(Boundary):
    """Freeze real development transformations separately from synthetic wire fixtures."""

    contract_version: Literal["we-e1-v1"] = "we-e1-v1"
    generator_version: Literal["we-e1-public-generator-v1"] = "we-e1-public-generator-v1"
    seed: Literal["we-e1-development-v1"] = "we-e1-development-v1"
    designation: Literal["W4NT3D-style_nonofficial_development_derivative"] = (
        "W4NT3D-style_nonofficial_development_derivative"
    )
    purpose: Literal["development_only_no_semantic_gold"] = "development_only_no_semantic_gold"
    pillow_version: str
    sources_registry_sha256: Digest
    license_ledger_sha256: Digest
    raw_inputs: tuple[EvidenceFile, ...]
    assets: tuple[PublicAsset, ...]
