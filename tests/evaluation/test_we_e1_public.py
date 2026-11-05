# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Negative controls use authored upstream-shaped data, never an acceptance dataset."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from scripts.we_e1.generate import ROOT, canonical, image_fixture
from scripts.we_e1.isolation import split_assets, split_overlap
from scripts.we_e1.models import SourceRegistry
from scripts.we_e1.public_generate import PublicBuild, build_public, write_public
from scripts.we_e1.public_inputs import (
    COMMONS_CANDIDATES,
    COMMONS_JPG,
    COMMONS_RAW,
    local_bytes,
    selected_rows,
)
from scripts.we_e1.public_models import LicenseLedger, PublicManifest
from scripts.we_e1.public_sources import build_sources
from scripts.we_e1.verify import reports, source_blockers, verify_local

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def upstream(tmp_path: Path) -> Path:
    """Create small explicitly synthetic responses for offline parser corruption tests."""
    files = {
        "proxy-hf/wiki40b-api.json": canonical(
            {"id": "google/wiki40b", "sha": "a" * 40, "private": False, "gated": False}
        ),
        "proxy-hf/wiki40b-card.md": b"### Licensing Information\n\n[More Information Needed]",
        "proxy-hf/wikipedia-copyrights.html": b"creativecommons.org/licenses/by-sa/4.0",
        "proxy-hf/cc-by-sa-4.0.html": b"ShareAlike; appropriate credit; changes",
        COMMONS_JPG: image_fixture(0),
    }
    for config in ("en", "zh-cn"):
        files[f"proxy-hf/{config}-train-0-4.json"] = canonical(
            {
                "partial": False,
                "rows": [
                    {
                        "row_idx": i,
                        "row": {
                            "wikidata_id": f"Q{i + 100}",
                            "version_id": str(1000 + i),
                            "text": f"\n_START_ARTICLE_\nAuthored {i}\nCafe\u0301 数据  ",
                        },
                    }
                    for i in range(4)
                ],
            }
        )
    raw = _commons(files[COMMONS_JPG])
    files[COMMONS_RAW] = canonical(raw)
    files[COMMONS_CANDIDATES] = canonical(raw)
    for name, data in files.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return tmp_path


def _commons(original: bytes) -> dict[str, object]:
    return {
        "query": {
            "pages": {
                "152924098": {
                    "pageid": 152924098,
                    "title": "File:Authored fixture.jpg",
                    "revisions": [{"revid": 1199020912, "timestamp": "2026-04-17T15:43:26Z"}],
                    "imageinfo": [
                        {
                            "size": len(original),
                            "width": 12,
                            "height": 7,
                            "sha1": hashlib.sha1(original, usedforsecurity=False).hexdigest(),
                            "url": "https://upload.wikimedia.org/authored-fixture.jpg",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Authored_fixture.jpg",
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC0"},
                                "License": {"value": "cc0"},
                                "Artist": {"value": "Authored test"},
                                "Categories": {
                                    "value": "CC-Zero|Self-published work|Interior lighting"
                                },
                                "LicenseUrl": {
                                    "value": "http://creativecommons.org/publicdomain/zero/1.0/deed.en"
                                },
                                "UsageTerms": {
                                    "value": "Creative Commons Zero, Public Domain Dedication"
                                },
                                "AttributionRequired": {"value": "false"},
                                "Restrictions": {"value": ""},
                                "Copyrighted": {"value": "True"},
                            },
                        }
                    ],
                }
            }
        }
    }


def test_public_regeneration_preserves_exact_original_utf8_and_raw_hashes(upstream: Path) -> None:
    """Original text includes all markers, combining characters and trailing spaces."""
    bundle = build_sources(upstream)
    row = selected_rows(upstream, "en").rows[0]
    assert bundle.files["derived/wiki40b-en-0.txt"] == row.row.text.encode()
    assert len(bundle.registry.sources[0].rows) == 8
    assert bundle.registry.sources[0].rows[0].revision == "a" * 40
    build = build_public(upstream)
    manifest = PublicManifest.model_validate_json(build.public_files["public-manifest.json"])
    assert len(manifest.raw_inputs) == 9
    assert len(manifest.assets) == 19
    assert build == build_public(upstream)


def test_card_silence_and_underlying_sharealike_are_distinct(upstream: Path) -> None:
    """A CC license is never invented for the dataset card."""
    record = build_sources(upstream).ledger.records[0]
    assert record.dataset_card_license == "not_declared_More_Information_Needed"
    assert record.license_id == "CC-BY-SA-4.0"
    assert len(record.obligations) == 3
    assert "NOT a license grant" in record.basis
    assert "history:" in record.attribution
    assert "opaque version_id" in record.attribution


def test_cc0_eligibility_keeps_original_url_and_independent_review_pending(upstream: Path) -> None:
    """Local admission retains all original declarations without awarding an audit pass."""
    bundle = build_sources(upstream)
    record = bundle.ledger.records[-1]
    assert record.license_url == "http://creativecommons.org/publicdomain/zero/1.0/deed.en"
    assert record.license_id == "CC0-1.0"
    assert record.eligible
    assert record.independent_license_review == "pending"
    assert "Copyrighted=True" in record.limitations[0]
    assert bundle.registry.sources[-1].status == "frozen"
    build = build_public(upstream)
    manifest = PublicManifest.model_validate_json(build.public_files["public-manifest.json"])
    images = [a for a in manifest.assets if a.modality == "image"]
    assert len(images) == 3
    assert all(a.license_eligible for a in images)
    assert all(a.original_group == "scene:interior-lighting" for a in images)
    assert b"6372844" not in build.public_files["public-manifest.json"]
    assert not any("mainline-commons" in item.path for item in manifest.raw_inputs)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("LicenseShortName", "Public domain"),
        ("License", "pd"),
        ("LicenseUrl", None),
        ("LicenseUrl", "https://example.org/cc0"),
        ("Categories", "CC-Zero|Copyrighted in Germany"),
        ("Restrictions", "Unresolved regional restriction"),
        ("UsageTerms", "All rights reserved"),
        ("AttributionRequired", "true"),
        ("Copyrighted", None),
        ("Copyrighted", "False"),
    ],
)
def test_cc0_missing_or_conflicting_license_fields_fail_closed(
    upstream: Path, field: str, value: str | None
) -> None:
    """A CC0 filename or short name cannot override missing URL or regional warnings."""
    data = json.loads((upstream / COMMONS_RAW).read_bytes())
    metadata = data["query"]["pages"]["152924098"]["imageinfo"][0]["extmetadata"]
    if value is None:
        del metadata[field]
    else:
        metadata[field]["value"] = value
    for name in (COMMONS_RAW, COMMONS_CANDIDATES):
        (upstream / name).write_bytes(canonical(data))
    with pytest.raises(ValueError, match="Commons CC0"):
        build_public(upstream)


@pytest.mark.parametrize("change", ["revision", "timestamp", "pageid", "candidate_metadata"])
def test_commons_revision_and_candidate_are_bound(upstream: Path, change: str) -> None:
    """Original and category snapshots must describe the same selected page and revision."""
    name = COMMONS_CANDIDATES if change == "candidate_metadata" else COMMONS_RAW
    data = json.loads((upstream / name).read_bytes())
    page = data["query"]["pages"]["152924098"]
    if change == "revision":
        page["revisions"][0]["revid"] += 1
    elif change == "timestamp":
        page["revisions"][0]["timestamp"] = "2026-01-01T00:00:00Z"
    elif change == "pageid":
        page["pageid"] = 6372844
    else:
        page["imageinfo"][0]["extmetadata"]["Credit"] = {"value": "Different source"}
    (upstream / name).write_bytes(canonical(data))
    with pytest.raises(ValueError, match="Commons"):
        build_public(upstream)


def test_public_components_include_cross_language_entity_copies(upstream: Path) -> None:
    """Shared entity groups and transform families cannot split across languages."""
    build = build_public(upstream)
    manifest = PublicManifest.model_validate_json(build.public_files["public-manifest.json"])
    assert split_assets(tuple(reversed(manifest.assets))) == manifest.assets
    assert not split_overlap(manifest.assets)
    assert {asset.split for asset in manifest.assets} == {"dev_tune", "dev_validation"}
    group = [a for a in manifest.assets if a.original_group == "wikidata:Q100"]
    assert len(group) == 4
    assert len({a.split for a in group}) == 1


def test_public_generator_never_opens_network(
    upstream: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Socket use would fail even when all original inputs are available."""

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("public generator attempted network")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    build_public(upstream)


@pytest.mark.parametrize("target", ["original", "raw_rows", "card", "copyrights", "license"])
def test_changed_upstream_bytes_fail_frozen_check(upstream: Path, target: str) -> None:
    """Hash changes or missing required license statements cannot reuse a frozen result."""
    out = upstream / "public"
    write_public(build_public(upstream), upstream, out, check=False)
    name = {
        "original": COMMONS_JPG,
        "raw_rows": "proxy-hf/en-train-0-4.json",
        "card": "proxy-hf/wiki40b-card.md",
        "copyrights": "proxy-hf/wikipedia-copyrights.html",
        "license": "proxy-hf/cc-by-sa-4.0.html",
    }[target]
    with (upstream / name).open("ab") as output:
        output.write(b" ")
    with pytest.raises(ValueError, match=r"Commons original|public frozen bytes differ"):
        write_public(build_public(upstream), upstream, out, check=True)


@pytest.mark.parametrize("target", ["metadata", "text", "variant", "manifest", "ledger", "sources"])
def test_rewritten_derived_claims_fail_reconstruction(upstream: Path, target: str) -> None:
    """Rehashing a forged derivative cannot replace independent derivation from raw data."""
    build = build_public(upstream)
    out = upstream / "public"
    write_public(build, upstream, out, check=False)
    name = {
        "metadata": "derived/wiki40b-en-0.metadata.json",
        "text": "derived/wiki40b-en-0.txt",
        "variant": "derived/variant-0-spacing-v1.bytes",
        "manifest": "public-manifest.json",
        "ledger": "license-ledger.json",
        "sources": "sources.json",
    }[target]
    base = upstream if name.startswith("derived/") else out
    (base / name).write_bytes(b"forged")
    with pytest.raises(ValueError, match="public frozen bytes differ"):
        write_public(build_public(upstream), upstream, out, check=True)


@pytest.mark.parametrize(
    "change", ["row_index", "partial", "revision", "license_name", "image_sha1"]
)
def test_raw_identity_or_license_corruption_fails(upstream: Path, change: str) -> None:
    """Malformed indices, source revisions and per-file declarations fail closed."""
    if change == "revision":
        path = upstream / "proxy-hf/wiki40b-api.json"
        data = json.loads(path.read_bytes())
        data["sha"] = "main"
    elif change in {"partial", "row_index"}:
        path = upstream / "proxy-hf/en-train-0-4.json"
        data = json.loads(path.read_bytes())
        if change == "partial":
            data["partial"] = True
        else:
            data["rows"][0]["row_idx"] = 99
    else:
        path = upstream / COMMONS_RAW
        data = json.loads(path.read_bytes())
        info = data["query"]["pages"]["152924098"]["imageinfo"][0]
        if change == "license_name":
            info["extmetadata"]["LicenseShortName"]["value"] = "All rights reserved"
        else:
            info["sha1"] = "0" * 40
    path.write_bytes(canonical(data))
    with pytest.raises(ValueError, match=r"validation error|selected row|Commons"):
        build_public(upstream)


def test_nonempty_evidence_never_awards_independent_acceptance(upstream: Path) -> None:
    """Actual rows and integrity checks are separate from custodian and CI approval."""
    build = build_public(upstream)
    out = upstream / "public"
    write_public(build, upstream, out, check=False)
    registry = SourceRegistry.model_validate_json(build.public_files["sources.json"])
    manifest = PublicManifest.model_validate_json(build.public_files["public-manifest.json"])
    result = reports(verify_local(), registry, source_blockers(registry, upstream), manifest)
    evidence = json.loads(canonical(result["development-public-evidence.json"]))
    assert len(evidence["public_rows"]) == 9
    assert len(evidence["restricted_candidate_rows"]) == 0
    assert evidence["eligible_public_originals"] == 9
    assert evidence["development_manifest_sha256"]
    assert json.loads(canonical(result["E1-exit.json"]))["e2_may_start"] is False
    assert json.loads(canonical(result["W-E-A9.json"]))["independent_intersection"] == "not_tested"
    assert LicenseLedger.model_validate_json(build.public_files["license-ledger.json"])


@pytest.mark.parametrize("public_gate", [False, True])
def test_cli_nonempty_public_evidence_keeps_public_gate_blocked(
    upstream: Path, *, public_gate: bool
) -> None:
    """Run the real CLI with authored evidence; public-gate must exit 2 with reports."""
    out = upstream / "public"
    write_public(build_public(upstream), upstream, out, check=False)
    shutil.copytree(ROOT / "generated", out / "generated")
    shutil.copyfile(ROOT / "search-space.json", out / "search-space.json")
    report_dir = upstream / "reports"
    # Relocate only the frozen contract root; all validation and CLI logic runs unchanged.
    bootstrap = (
        "import sys; from pathlib import Path; sys.path.insert(0, sys.argv.pop(1)); "
        "from scripts.we_e1 import verify; verify.ROOT = Path(sys.argv.pop(1)); verify.main()"
    )
    command = [
        sys.executable,
        "-I",
        "-B",
        "-c",
        bootstrap,
        str(ROOT.parents[1]),
        str(out),
        "--development-root",
        str(upstream),
        "--report-dir",
        str(report_dir),
    ]
    if public_gate:
        command.append("--public-gate")
    result = subprocess.run(  # noqa: S603  # Fixed interpreter, local authored evidence only.
        command, capture_output=True, text=True, check=False, timeout=30
    )
    assert result.returncode == (2 if public_gate else 0), result.stdout + result.stderr
    evidence = json.loads((report_dir / "development-public-evidence.json").read_bytes())
    assert len(evidence["public_rows"]) == 9
    assert evidence["source_license_validation"] == "checked"
    exit_report = json.loads((report_dir / "E1-exit.json").read_bytes())
    assert exit_report["status"] == "blocked"
    assert exit_report["e2_may_start"] is False
    assert exit_report["real_quality"] == "not_tested"


@pytest.mark.parametrize("name", ["../outside", "/outside"])
def test_public_input_rejects_escaped_paths(upstream: Path, name: str) -> None:
    """No relative traversal or absolute source is accepted."""
    with pytest.raises(ValueError, match="relative"):
        local_bytes(upstream, name)


def test_public_input_rejects_symlink(upstream: Path) -> None:
    """A named source cannot redirect reading outside its actual original bytes."""
    (upstream / "linked").symlink_to(upstream / COMMONS_JPG)
    with pytest.raises(ValueError, match="symlink"):
        local_bytes(upstream, "linked")


def test_public_tree_contains_only_small_references() -> None:
    """Large image and text bodies remain in the explicitly supplied development root."""
    for name in (
        "public-manifest.json",
        "license-ledger.json",
        "sources.json",
        "public-hashes.json",
    ):
        assert (ROOT / name).stat().st_size < 100_000
    assert set(PublicBuild.model_fields) == {"public_files", "retained_files"}
