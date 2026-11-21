# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recipient CLI stays independent of settings, database and model services."""

import json
import sys
from pathlib import Path

import pytest

from datakeel import cli
from datakeel.core.delivery_models import DeliveryManifest, DeliveryRecords
from datakeel.core.release_models import DeliveryReviewProof
from datakeel.core.training_models import SplitDistribution
from datakeel.delivery.manifest import manifest_hash


def test_offline_cli_ignores_invalid_service_settings_and_database(
    package: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Even invalid platform configuration cannot prevent local recipient verification."""

    def forbidden() -> None:
        pytest.fail("Offline reconcile attempted platform initialization")

    monkeypatch.setenv("DATAKEEL_DATABASE_URL", "invalid-database")
    monkeypatch.setenv("DATAKEEL_MODEL_ROUTING_FILE", "/nonexistent-routing-file")
    monkeypatch.setattr(cli, "Database", forbidden)
    monkeypatch.setattr(cli, "configure_logging", forbidden)
    monkeypatch.setattr(cli, "load_config", forbidden)
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package), "--json"])
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["passed"] is True
    assert len(result["categories"]) == 6


def test_offline_cli_corruption_exits_one_with_readable_differences(
    package: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Human-facing output is bilingual and unsuccessful delivery has a failing exit status."""
    (package / "files/0.txt").write_bytes(b"changed")
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "FAIL" in output
    assert "内容哈希" in output
    assert "files/0.txt" in output


def test_invalid_delivery_cli_exits_two_without_dumping_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Malformed contracts yield a useful machine error without exposing their contents."""
    (tmp_path / "MANIFEST.json").write_text('{"private": "sensitive-input"}')
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(tmp_path), "--json"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    output = capsys.readouterr().out
    assert json.loads(output)["error"] == "invalid_delivery"
    assert "sensitive-input" not in output


def _attach_review(package: Path, *, version_id: str = "version-one", count: int = 1) -> None:
    manifest = DeliveryManifest.model_validate_json((package / "MANIFEST.json").read_bytes())
    records = DeliveryRecords.model_validate_json((package / "RECORDS.json").read_bytes())
    proof = DeliveryReviewProof(
        version_id=version_id,
        split_id="split-one",
        split_algorithm_version="1.0",
        checked_signals=("exact", "image"),
        image_threshold=8,
        distributions=(
            SplitDistribution(split="train", count=count),
            SplitDistribution(split="test", count=1),
        ),
        sample_count=2,
    ).model_dump(mode="json")
    updated = manifest.model_copy(update={"metadata": {"delivery_review": proof}})
    updated = updated.model_copy(update={"manifest_sha256": manifest_hash(updated)})
    (package / "MANIFEST.json").write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    (package / "RECORDS.json").write_text(
        records.model_copy(update={"metadata": {"delivery_review": proof}}).model_dump_json(
            indent=2
        ),
        encoding="utf-8",
    )


def test_reconcile_verifies_and_renders_delivery_review_proof_and_tamper(
    package: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid delivery_review proof renders in CLI/JSON; mismatched version fails metadata."""
    _attach_review(package)
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package)])
    cli.main()
    human = capsys.readouterr().out
    assert "交付审查证明 / Delivery review: directory-leakage-v1" in human
    assert "train=1, test=1" in human

    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package), "--json"])
    cli.main()
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["passed"] is True
    assert parsed["delivery_review"]["split_id"] == "split-one"

    _attach_review(package, version_id="other-version")
    monkeypatch.setattr(sys, "argv", ["datakeel", "reconcile", str(package), "--json"])
    with pytest.raises(SystemExit) as failed:
        cli.main()
    assert failed.value.code == 1
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["passed"] is False
    assert "delivery_review" not in rejected
