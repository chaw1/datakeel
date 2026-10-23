# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load versioned deterministic evidence vocabulary and image matching settings."""

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from datakeel.core.models import BoundaryModel

PACKAGE_ROOT = Path(__file__).resolve().parents[2]


class Concept(BoundaryModel):
    """Normalize caption aliases and annotation categories to one concept identity."""

    id: str
    kind: Literal["object", "scene"]
    synonyms: tuple[str, ...]
    annotation_categories: tuple[str, ...]


class Lexicon(BoundaryModel):
    """Version the shared caption and annotation vocabulary."""

    schema_version: Literal["1.0"]
    concepts: tuple[Concept, ...]


class NearDuplicateContract(BoundaryModel):
    """Pin the perceptual-hash algorithm, blocking policy, and direct-pair threshold."""

    schema_version: Literal["1.0"]
    algorithm: Literal["dhash"]
    bits: Literal[64]
    width: Literal[9]
    height: Literal[8]
    resampling: Literal["lanczos"]
    hamming_threshold: int = Field(ge=0, le=64)
    prefix_bits: int = Field(ge=1, le=16)


def contract_path(name: str) -> Path:
    """Locate repository contracts or the identical packaged wheel resources."""
    source = PACKAGE_ROOT.parent / "contracts" / "evidence" / name
    return source if source.exists() else PACKAGE_ROOT / "_contracts" / "evidence" / name


def read_lexicon() -> Lexicon:
    """Validate the current on-disk lexicon without hiding contract edits in a cache."""
    return Lexicon.model_validate(yaml.safe_load(contract_path("lexicon.yaml").read_text()))


def read_near_duplicate() -> NearDuplicateContract:
    """Read the single authoritative matching threshold and blocking policy."""
    return NearDuplicateContract.model_validate(
        yaml.safe_load(contract_path("near_duplicate.yaml").read_text())
    )


def contract_hashes() -> tuple[str, str]:
    """Return lexicon and near-duplicate contract content hashes in that order."""
    lexicon = hashlib.sha256(contract_path("lexicon.yaml").read_bytes()).hexdigest()
    matching = hashlib.sha256(contract_path("near_duplicate.yaml").read_bytes()).hexdigest()
    return lexicon, matching
