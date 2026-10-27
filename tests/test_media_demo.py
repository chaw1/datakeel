# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated media demonstrates measured defects and an isolated offline workflow."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud.io import load_cloud
from scripts.demo_media import MediaDemoResult, generate_media, run_demo


def test_generated_media_is_deterministic_and_contains_distinct_defects(tmp_path: Path) -> None:
    """Keep fixtures synthetic, repeatable and representative of coordinate defects."""
    first = generate_media(tmp_path / "first")
    second = generate_media(tmp_path / "second")
    assert len(first) == 13
    assert [path.read_bytes() for path in first] == [path.read_bytes() for path in second]
    clouds = {path.stem: load_cloud(path).xyz for path in first if path.suffix in {".ply", ".pcd"}}
    normal = clouds["room-normal"]
    assert np.all(np.isfinite(normal))
    np.testing.assert_allclose(clouds["room-millimeters"], normal * 1000)
    assert np.ptp(clouds["room-outliers"], axis=0).min() > 300
    assert np.count_nonzero(~np.isfinite(clouds["room-invalid"]).all(axis=1)) > 1000
    assert len(clouds["room-sparse"]) < len(normal) / 50
    with Image.open(tmp_path / "first" / "image-low-resolution.png") as small:
        assert small.size == (64, 48)
    with Image.open(tmp_path / "first" / "image-solid.png") as solid:
        assert np.std(np.asarray(solid)) == 0


def test_media_cli_runs_the_full_offline_pipeline_despite_inherited_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI ignores inherited services and captures every generated defect in its report."""
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", "postgresql://example.invalid/unused")
    monkeypatch.setenv("DATAKEEL_S3_BUCKET", "unused-example-bucket")
    monkeypatch.setenv("DATAKEEL_LLM_URL", "https://example.invalid/unused")
    monkeypatch.setenv("DATAKEEL_OPENAI_API_KEY", "unused-example-value")
    output = tmp_path / "media"
    completed = subprocess.run(  # noqa: S603  # Fixed local demo script and temporary output path.
        [sys.executable, "scripts/demo_media.py", "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    summary = MediaDemoResult.model_validate_json((output / "summary.json").read_text())
    assert MediaDemoResult.model_validate_json(completed.stdout) == summary
    assert summary.state == "COMPLETED"
    assert summary.source_files == 13
    assert summary.pointcloud_files == 5
    assert summary.image_files == 8
    assert summary.versions == 2
    assert summary.lineage_events >= 6
    assert summary.offline
    assert {
        "image_blur",
        "image_exposure",
        "image_noise",
        "image_resolution",
        "image_solid_color",
        "pointcloud_invalid_ratio",
        "pointcloud_outlier_ratio",
        "pointcloud_sparse",
        "pointcloud_unit",
    } <= set(summary.issue_codes)
    issues = summary.file_issues
    assert issues["room-normal.ply"] == issues["image-clear.png"] == []
    assert issues["room-millimeters.pcd"] == ["pointcloud_unit"]
    assert issues["room-outliers.ply"] == ["pointcloud_outlier_ratio"]
    assert issues["room-invalid.pcd"] == ["pointcloud_invalid_ratio"]
    assert issues["room-sparse.ply"] == ["pointcloud_sparse"]
    for filename, code in (
        ("image-blur-mild.png", "image_blur"),
        ("image-blur-strong.png", "image_blur"),
        ("image-overexposed.png", "image_exposure"),
        ("image-underexposed.png", "image_exposure"),
        ("image-noisy.png", "image_noise"),
        ("image-low-resolution.png", "image_resolution"),
        ("image-solid.png", "image_solid_color"),
    ):
        assert code in issues[filename]
    report = json.loads((output / "report.json").read_text())
    assert report["source"] == "baseline"
    assert report["llm_body"] is None
    assert "点云 / Point clouds" in (output / "report.md").read_text()
    assert (output / "quality.json").is_file()
    assert (output / "versions.json").is_file()
    assert (output / "lineage.json").is_file()
    assert (output / "state" / "datakeel.db").is_file()


def test_media_demo_rejects_a_nonisolated_direct_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Programmatic use cannot silently select an unrelated application configuration."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "other-home"))
    with pytest.raises(ValidationError, match="isolated local configuration"):
        run_demo(tmp_path / "demo")
    assert not (tmp_path / "demo").exists()


def test_media_cli_preserves_existing_output_files(tmp_path: Path) -> None:
    """Re-running a demo cannot overwrite a populated local directory."""
    marker = tmp_path / "existing.txt"
    marker.write_text("preserve this file")
    completed = subprocess.run(  # noqa: S603  # Fixed local demo script and temporary output path.
        [sys.executable, "scripts/demo_media.py", "--output", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode != 0
    assert "new or empty directory" in completed.stderr
    assert marker.read_text() == "preserve this file"
    assert not (tmp_path / "summary.json").exists()
