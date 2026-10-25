# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep existing text cache bytes stable while image semantics remain explicitly versioned."""

from pathlib import Path

import pytest
import yaml

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.kg_models import TextBlock
from datakeel.kg.cache import build_cache_key, extraction_identity
from datakeel.kg.loader import get_profile, get_schema, load_profile
from datakeel.kg.prompt import IMAGE_DIRECTION_RULE, extraction_prompt, image_profile
from datakeel.storage.kg_preparation import read_recording


def test_default_text_cache_key_matches_main_byte_for_byte() -> None:
    """Freeze the key computed from main's v0.11.0 models, profile, schema and recording."""
    schema, profile = get_schema("business-knowledge"), get_profile("replay-demo")
    recording_hash = read_recording(profile)[0]
    identity = extraction_identity(schema, profile, recording_hash)
    expected_identity = ExtractorRef(
        id="evidence.kg",
        version="1:58eb2d4f977b9577fd90d800ef3ac3b52311508118ad1d04e351519ce10b8824",
    )
    assert identity == expected_identity
    key = build_cache_key(
        TextBlock(text="Example.", start=0, end=8), schema, profile, identity, recording_hash
    )
    assert key.schema_hash == "9269cb194d9ebfc2ebb8a5813254aada2e8f76e2a2815d2b4335959ffbf6e227"
    assert key.profile_hash == "fd043b63b71ae7badc7cbc61c0d93112cd3f037b02d3e349365996d3783b741d"
    assert key.digest() == "22c962b98c45c9f3e71900eeb9d1c3e435029e8af83f6add592a82253a5c922e"


def test_explicit_person_marker_still_changes_extraction_identity() -> None:
    """Only the false default is omitted; true person semantics must invalidate old results."""
    schema, profile = get_schema(), image_profile(get_profile("replay-demo"))
    changed = schema.model_copy(
        update={
            "entity_types": (
                schema.entity_types[0].model_copy(update={"person": False}),
                *schema.entity_types[1:],
            )
        }
    )
    assert extraction_identity(schema, profile) != extraction_identity(changed, profile)


@pytest.mark.parametrize("change", ["missing", "domain", "range"])
def test_image_arrow_rule_requires_dataset_derived_from_schema(change: str) -> None:
    """Image prompts cannot prescribe relation vocabulary or directions absent from the schema."""
    schema = get_schema()
    relations = tuple(
        item.model_copy(update={change: ("system",)})
        if item.name == "derived_from" and change != "missing"
        else item
        for item in schema.relations
        if not (change == "missing" and item.name == "derived_from")
    )
    altered = schema.model_copy(update={"relations": relations})
    block = TextBlock(text="A --> B", start=0, end=7)
    assert IMAGE_DIRECTION_RULE in extraction_prompt(block, schema, "image-kg-v1")
    assert IMAGE_DIRECTION_RULE not in extraction_prompt(block, altered, "image-kg-v1")


def test_loading_extraction_profile_rejects_unknown_prompt_version(tmp_path: Path) -> None:
    """Configuration errors fail at the YAML boundary, before providers or caches exist."""
    content = get_profile("fake").model_dump(mode="json")
    content["prompt_version"] = "unrecognized-prompt"
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(content))
    with pytest.raises(ValidationError, match="prompt_version"):
        load_profile(path)
