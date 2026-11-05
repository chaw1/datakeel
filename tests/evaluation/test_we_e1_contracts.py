# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise E1 offline contracts; all test evidence is authored and synthetic."""

from __future__ import annotations

import base64
import json
import socket
import struct
from io import BytesIO
from typing import TYPE_CHECKING, Literal

import pytest
from PIL import Image
from pydantic import ValidationError

from scripts.we_e1.generate import ROOT, build, canonical, image_fixture
from scripts.we_e1.isolation import IndependentSummary, split_assets, split_overlap
from scripts.we_e1.models import EvidenceFile, Manifest, SearchSpace, Source, SourceRegistry
from scripts.we_e1.preprocess import ContractError, Prepared, prepare_image, prepare_text, sha256
from scripts.we_e1.protocol import (
    Embedding,
    ImageInput,
    ImageRequest,
    Response,
    TextRequest,
    WireExample,
    validate_response,
)
from scripts.we_e1.verify import evidence_bytes, reports, source_blockers, verify_local

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def wire() -> WireExample:
    """Load only the generated development-side fake wire envelope."""
    return WireExample.model_validate_json(build()["fake-wire.json"])


def test_generator_frozen_bytes_and_schemas_are_current() -> None:
    """Regeneration must reproduce every checked-in byte and schema."""
    assert build() == build()
    assert len(verify_local().assets) == 24


def test_offline_verification_never_constructs_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """An attempted network call fails the test, independently of fake response values."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("E1 attempted network access")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    verify_local()


def test_text_preserves_utf8_combining_characters_whitespace_and_newlines() -> None:
    """No normalization or prefixing is implicit."""
    text = " cafe\u0301\n数据  "
    prepared = prepare_text(text, tokenizer="fake-codepoint-v1")
    assert base64.b64decode(prepared.payload_base64) == text.encode()
    assert prepared.payload_sha256 != sha256(text.replace("e\u0301", "é").encode())
    assert not prepared.prefix_only


@pytest.mark.parametrize(
    ("text", "tokenizer", "reason"),
    [
        ("text", None, "token_bound_unknown"),
        ("", "fake-codepoint-v1", "empty_input"),
        ("x" * 8193, "fake-codepoint-v1", "too_long_no_automatic_prefix"),
    ],
)
def test_text_unknown_or_excessive_bound_is_typed_failure(
    text: str,
    tokenizer: Literal["fake-codepoint-v1"] | None,
    reason: str,
) -> None:
    """Reject an unprovable token bound instead of truncating or using zero tokens."""
    with pytest.raises(ContractError, match=reason):
        prepare_text(text, tokenizer=tokenizer)


def test_image_non_square_exif_rotation_metadata_strip_and_data_uri() -> None:
    """The colored corner detects a missing or reversed EXIF rotation."""
    prepared = prepare_image(image_fixture(0, orientation=6))
    payload = base64.b64decode(prepared.payload_base64)
    with Image.open(BytesIO(payload)) as image:
        assert image.size == (7, 12)
        assert image.getpixel((6, 0)) == (255, 0, 0)
        assert not image.info
        assert not image.getexif()
    assert prepared.data_uri == "data:image/png;base64," + prepared.payload_base64
    assert prepared.payload_sha256 == sha256(payload)
    assert prepared == prepare_image(payload)


def test_image_max_side_preserves_aspect_ratio_and_checks_final_size() -> None:
    """The fake image rule resizes the full frame without center cropping."""
    image = Image.new("RGB", (1024, 256), "red")
    original = BytesIO()
    image.save(original, format="PNG")
    prepared = prepare_image(original.getvalue())
    payload = base64.b64decode(prepared.payload_base64)
    with Image.open(BytesIO(payload)) as result:
        assert result.size == (512, 128)
    assert len(payload) <= 3_000_000


def test_image_rejects_over_limit_postprocessed_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reduced test cap proves the checked limit applies after preprocessing."""
    monkeypatch.setattr("scripts.we_e1.preprocess.MAX_IMAGE_BYTES", 1)
    with pytest.raises(ContractError, match="image_payload_too_large"):
        prepare_image(image_fixture(0))


@pytest.mark.parametrize("payload", ["!!!", "", "a", "YQ", "YQ==\n", "YQ==!", "数据"])
def test_image_input_and_request_reject_invalid_or_empty_base64(payload: str) -> None:
    """The standalone boundary rejects bad payloads without prepared-wire validation."""
    image = "data:image/png;base64," + payload
    with pytest.raises(ValidationError):
        ImageInput(image=image)
    with pytest.raises(ValidationError):
        ImageRequest.model_validate_json(
            canonical({"model": "multimodal-embedding-v1", "input": [{"image": image}]})
        )


def test_image_input_accepts_valid_prepared_base64(wire: WireExample) -> None:
    """Strict decoding retains a valid Data URI byte for byte."""
    image = wire.image_request.input[0].image
    assert ImageInput(image=image).image == image


def test_response_mapping_is_local_index_and_f32_little_endian(wire: WireExample) -> None:
    """Canonical vector hash comes from F32 bytes, not decimal JSON or a server claim."""
    hashes = (wire.text_prepared.payload_sha256,)
    mapping = validate_response(wire.text_response, wire.text_request, hashes)[0]
    assert mapping.payload_sha256 == hashes[0]
    assert mapping.vector_f32le_sha256 == sha256(struct.pack("<64f", 1.0, *([0.0] * 63)))


@pytest.mark.parametrize("kind", ["hash", "base64", "uri"])
def test_prepared_payload_mapping_rejects_corruption(wire: WireExample, kind: str) -> None:
    """A frozen byte hash and Data URI must agree with actual local payload bytes."""
    data = wire.image_prepared.model_dump(mode="json")
    update = {
        "hash": {"payload_sha256": "0" * 64},
        "base64": {"payload_base64": "!"},
        "uri": {"data_uri": "data:image/png;base64,changed"},
    }[kind]
    with pytest.raises(ValidationError):
        Prepared.model_validate_json(canonical(data | update))


@pytest.mark.parametrize("kind", ["count", "index", "dimension", "model", "hash_count"])
def test_response_mapping_mismatch_never_supplies_a_vector(wire: WireExample, kind: str) -> None:
    """Malformed response mappings produce typed failures."""
    response = wire.text_response.model_dump(mode="json")
    if kind == "count":
        response["data"] = []
    elif kind == "index":
        response["data"][0]["index"] = 1
    elif kind == "dimension":
        response["data"][0]["embedding"] = [1.0]
    elif kind == "model":
        response["model"] = "multimodal-embedding-v1"
    parsed = Response.model_validate_json(canonical(response))
    hashes = () if kind == "hash_count" else (wire.text_prepared.payload_sha256,)
    with pytest.raises(ContractError, match=r"response_.*_mismatch"):
        validate_response(parsed, wire.text_request, hashes)


def test_response_permutation_uses_index_not_return_order(wire: WireExample) -> None:
    """Reordered results bind to the correct local payload and duplicate indices fail."""
    first = wire.text_response.data[0]
    second = first.model_copy(update={"index": 1, "embedding": (0.0, 1.0) + (0.0,) * 62})
    response = wire.text_response.model_copy(update={"data": (second, first)})
    request = wire.text_request.model_copy(update={"input": ("one", "two")})
    hashes = (sha256(b"one"), sha256(b"two"))
    assert tuple(m.payload_sha256 for m in validate_response(response, request, hashes)) == hashes
    duplicated = response.model_copy(update={"data": (first, first)})
    with pytest.raises(ContractError, match="response_index_mismatch"):
        validate_response(duplicated, request, hashes)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 0.0, 1e100, 1e-100])
def test_nonfinite_zero_overflow_and_underflow_vectors_are_rejected(value: float) -> None:
    """F32 conversion must remain finite and nonzero."""
    with pytest.raises(ValidationError):
        Embedding(object="embedding", index=0, embedding=(value,))


@pytest.mark.parametrize("kind", ["missing", "negative", "invented", "bool"])
def test_usage_missing_invalid_or_invented_is_rejected(wire: WireExample, kind: str) -> None:
    """No assumption of request_id or input/output token aliases is permitted."""
    response = wire.text_response.model_dump(mode="json")
    if kind == "missing":
        del response["usage"]
    elif kind == "invented":
        response["usage"] = {"input_tokens": 1, "output_tokens": 0}
    else:
        response["usage"] = {"total_tokens": -1 if kind == "negative" else True}
    with pytest.raises(ValidationError):
        Response.model_validate_json(canonical(response))


def test_request_rejects_large_batch_unknown_fields_and_non_discrete_dimensions(
    wire: WireExample,
) -> None:
    """The request subset fails closed instead of silently changing the provider contract."""
    for update in ({"input": ["x"] * 11}, {"dimensions": 65}, {"input": [""]}, {"secret": "x"}):
        request = wire.text_request.model_dump(mode="json") | update
        with pytest.raises(ValidationError):
            TextRequest.model_validate_json(canonical(request))


def test_boundary_models_are_immutable_and_real_egress_cannot_be_enabled(wire: WireExample) -> None:
    """Strict fake envelopes cannot become real plans through extra fields or coercion."""
    with pytest.raises(ValidationError):
        wire.real_budget_cny = 0
    data = wire.model_dump(mode="json") | {"mode": "real", "real_egress_enabled": True}
    with pytest.raises(ValidationError):
        WireExample.model_validate_json(canonical(data))


def test_development_split_keeps_all_identity_components_and_is_order_invariant() -> None:
    """Group-level partitions have no source/content/family overlap."""
    manifest = Manifest.model_validate_json(build()["manifest.json"])
    assert not split_overlap(manifest.assets)
    assert split_assets(tuple(reversed(manifest.assets))) == manifest.assets
    assert len({a.original_group for a in manifest.assets}) == 12


def test_transitive_group_links_cannot_cross_development_splits() -> None:
    """A bridge through different identity dimensions unifies the entire component."""
    assets = Manifest.model_validate_json(build()["manifest.json"]).assets
    first = assets[0]
    second = assets[4].model_copy(update={"transformation_family": first.transformation_family})
    third = assets[8].model_copy(update={"near_duplicate_cluster": second.near_duplicate_cluster})
    split = split_assets((third, first, second))
    assert len({a.split for a in split}) == 1
    assert not split_overlap(split)


def test_split_overlap_detects_a_deliberately_broken_group() -> None:
    """A negative control proves the development disjointness checker is meaningful."""
    first = Manifest.model_validate_json(build()["manifest.json"]).assets[0]
    other = first.model_copy(update={"asset_id": "negative-control", "split": "dev_validation"})
    first = first.model_copy(update={"split": "dev_tune"})
    assert split_overlap((first, other))


def test_public_sources_remain_blocked_without_reading_missing_evidence(tmp_path: Path) -> None:
    """The offline contract can pass while the E1 public-data exit remains blocked."""
    registry = _blocked_registry()
    blockers = source_blockers(registry, tmp_path / "not-created")
    assert len(blockers) >= 2
    assert all(s.status == "blocked" and not s.rows for s in registry.sources)
    result = json.loads(canonical(reports(verify_local(), registry, blockers)))
    assert result["E1-exit.json"]["e2_may_start"] is False
    assert result["development-public-evidence.json"]["public_rows"] == []


def test_public_frozen_claim_without_revision_rows_and_license_is_rejected() -> None:
    """A URL and an asserted license name do not freeze a dataset."""
    with pytest.raises(ValidationError, match="frozen source requires"):
        Source(source_id="wiki40b-style", planned_url="https://example.org/data", status="frozen")


def test_network_attempt_does_not_satisfy_the_public_gate(tmp_path: Path) -> None:
    """An acquisition attempt cannot stand in for original bytes or license evidence."""
    registry = _blocked_registry()
    for attempted in (False, True):
        recorded = registry.model_copy(update={"network_performed": attempted})
        blockers = source_blockers(recorded, tmp_path / "not-created")
        result = json.loads(canonical(reports(verify_local(), recorded, blockers)))
        assert result["development-public-evidence.json"]["status"] == "blocked"
        assert result["development-public-evidence.json"]["public_rows"] == []
        assert result["E1-exit.json"]["e2_may_start"] is False


def _blocked_registry() -> SourceRegistry:
    return SourceRegistry(
        contract_version="we-e1-v1",
        network_performed=False,
        sources=tuple(
            Source(
                source_id=source.source_id,
                planned_url=source.planned_url,
                status="blocked",
                blockers=("synthetic regression: no retained evidence",),
            )
            for source in SourceRegistry.model_validate_json(
                (ROOT / "sources.json").read_bytes()
            ).sources
        ),
    )


def test_upstream_evidence_hash_and_path_checks_fail_closed(tmp_path: Path) -> None:
    """Only exact hash-bound files within the development evidence root are readable."""
    content = b"authored license-check fixture, not upstream evidence"
    (tmp_path / "test.txt").write_bytes(content)
    valid = EvidenceFile(path="test.txt", sha256=sha256(content))
    assert evidence_bytes(valid, tmp_path) == content
    for path, digest in (("../outside", sha256(content)), ("test.txt", "0" * 64)):
        with pytest.raises(ValueError, match="upstream evidence"):
            evidence_bytes(EvidenceFile(path=path, sha256=digest), tmp_path)
    (tmp_path / "linked.txt").symlink_to(tmp_path / "test.txt")
    with pytest.raises(ValueError, match="symlinks"):
        evidence_bytes(valid.model_copy(update={"path": "linked.txt"}), tmp_path)


def test_search_space_is_finite_unselected_and_rejects_invalid_thresholds() -> None:
    """Freeze the search grid before tuning, without inventing quality gates."""
    data = json.loads((ROOT / "search-space.json").read_bytes())
    assert SearchSpace.model_validate_json(canonical(data)).selected_parameters is None
    for values in ([], [0.9, 0.9], [1.1], [-0.1]):
        with pytest.raises(ValidationError):
            SearchSpace.model_validate_json(canonical(data | {"duplicate_threshold": values}))


def test_independent_summary_cannot_pass_empty_public_data_or_overlaps() -> None:
    """This constructs synthetic schema tests, never an independent acceptance result."""
    data = {
        "contract_version": "we-e1-v1",
        "development_evidence_sha256": "0" * 64,
        "development_manifest_sha256": "0" * 64,
        "spec_bundle_sha256": "0" * 64,
        "auditor_session": "synthetic-schema-test-only",
        "checked_dimensions": [
            "stable_source",
            "original_content",
            "transformation_family",
            "semantic_group",
            "near_duplicate_cluster",
        ],
        "development_public_rows": 1,
        "holdout_rows": 1,
        "overlap_counts": [0] * 5,
        "command_audit_complete": True,
        "holdout_access_by_implementer": False,
        "result": "pass",
    }
    IndependentSummary.model_validate_json(canonical(data))
    for update in (
        {"development_public_rows": 0},
        {"overlap_counts": [0, 1, 0, 0, 0]},
        {"command_audit_complete": False},
        {"holdout_access_by_implementer": True},
        {"checked_dimensions": ["stable_source"]},
    ):
        with pytest.raises(ValidationError):
            IndependentSummary.model_validate_json(canonical(data | update))
