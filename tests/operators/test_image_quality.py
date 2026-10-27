# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated photographic defects exercise five independent image-quality signals."""

from __future__ import annotations

import itertools
from io import BytesIO
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image, ImageFilter
from pydantic import ValidationError as SchemaValidationError

from datakeel.operators import REGISTRY
from datakeel.operators.base import ImageQualityParams
from datakeel.operators.image.quality import ImageQualityMeasurement

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import JsonValue

    from tests.operators.factories import FileFactory


def _board(size: tuple[int, int] = (512, 384), contrast: int = 144) -> Image.Image:
    y, x = np.indices((size[1], size[0]))
    cells = (x // max(1, size[0] // 32) + y // max(1, size[1] // 24)) % 2
    gray = np.where(cells, 128 - contrast // 2, 128 + contrast // 2).astype(np.uint8)
    return Image.fromarray(np.repeat(gray[..., None], 3, axis=2))


def _quality(
    image: Image.Image,
    make_file: FileFactory,
    output_dir: Path,
    params: dict[str, JsonValue] | None = None,
) -> ImageQualityMeasurement:
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    file = make_file(encoded.getvalue(), "generated.png", "image")
    result = REGISTRY["image.quality"].run([file], output_dir, params)
    return ImageQualityMeasurement.model_validate(result.files[0].metadata["image_quality"])


def test_gaussian_blur_increasing_strength_strictly_lowers_sharpness_score(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Compare the same scene at progressively wider Gaussian point-spread functions."""
    measurements = [
        _quality(_board().filter(ImageFilter.GaussianBlur(radius)), make_file, output_dir)
        for radius in (0, 0.7, 1.5, 3, 7)
    ]
    scores = [value.scores["blur"] for value in measurements]
    assert all(left > right for left, right in itertools.pairwise(scores))
    assert measurements[0].checks.blur.failed is False
    assert measurements[-1].checks.blur.failed is True
    assert measurements[-1].score < 60


@pytest.mark.parametrize("levels", [(128, 80, 30, 5), (128, 175, 225, 250)])
def test_exposure_farther_from_midgray_strictly_lowers_score(
    make_file: FileFactory, output_dir: Path, levels: tuple[int, ...]
) -> None:
    """Catch both increasing darkness and increasing overexposure independently of texture."""
    measurements = [
        _quality(Image.new("RGB", (256, 256), (level,) * 3), make_file, output_dir)
        for level in levels
    ]
    scores = [value.scores["exposure"] for value in measurements]
    assert all(left > right for left, right in itertools.pairwise(scores))
    assert measurements[0].checks.exposure.failed is False
    assert measurements[-1].checks.exposure.failed is True


def test_clipped_highlights_and_shadows_fail_even_with_balanced_mean(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Use histogram tails so balanced clipping cannot hide behind a plausible average."""
    pixels = np.zeros((256, 256, 3), dtype=np.uint8)
    pixels[:, 128:] = 255
    quality = _quality(
        Image.fromarray(pixels), make_file, output_dir, {"max_clipped_fraction": 0.2}
    )
    assert quality.brightness == 127.5
    assert quality.checks.exposure.failed is True
    assert "0.5000/0.5000" in quality.checks.exposure.reason


def test_increasing_gaussian_noise_strictly_lowers_noise_score(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Estimate stochastic high frequencies from native neighboring pixels before resizing."""
    pixels = np.asarray(_board()).astype(np.float32)
    noise = np.random.default_rng(207).normal(size=pixels.shape)
    measurements = [
        _quality(
            Image.fromarray(np.clip(pixels + sigma * noise, 0, 255).astype(np.uint8)),
            make_file,
            output_dir,
        )
        for sigma in (0, 3, 9, 21, 45)
    ]
    scores = [value.scores["noise"] for value in measurements]
    assert all(left > right for left, right in itertools.pairwise(scores))
    assert measurements[0].noise_sigma == 0
    assert measurements[-1].checks.noise.failed is True
    assert measurements[-1].score < 60


def test_resolution_score_tracks_shortest_side_and_configured_minimum(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Grade usable spatial resolution against the configured target instead of file bytes."""
    values = [_quality(_board((side * 2, side)), make_file, output_dir) for side in (8, 16, 32, 64)]
    assert [value.scores["resolution"] for value in values] == [12.5, 25, 50, 100]
    assert [value.checks.resolution.failed for value in values] == [True, True, True, False]


def test_pure_and_near_pure_color_score_increases_with_visible_variation(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Distinguish a constant image and increasingly visible scene contrast."""
    values = [_quality(_board(contrast=value), make_file, output_dir) for value in (0, 2, 6, 32)]
    scores = [value.scores["solid_color"] for value in values]
    assert all(left < right for left, right in itertools.pairwise(scores))
    assert values[0].checks.solid_color.failed is True
    assert values[-1].checks.solid_color.failed is False
    assert values[0].score == 0


def test_normalized_sharpness_is_stable_when_same_scene_is_rendered_larger(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Compare equal relative detail at two native resolutions on the same analysis canvas."""
    small = _quality(_board(), make_file, output_dir)
    large = _quality(_board((1024, 768)), make_file, output_dir)
    assert (small.analysis_width, small.analysis_height) == (512, 384)
    assert (large.analysis_width, large.analysis_height) == (512, 384)
    assert large.scores["blur"] == pytest.approx(small.scores["blur"], rel=0.03)


def test_small_sharp_image_fails_resolution_without_interpolated_blur(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Images below the analysis size are measured natively instead of being enlarged."""
    small = _quality(_board((48, 36)), make_file, output_dir)
    assert (small.analysis_width, small.analysis_height) == (48, 36)
    assert small.checks.resolution.failed is True
    assert small.checks.blur.failed is False
    assert "48x36" in small.checks.blur.reason


def test_noise_estimate_is_stable_across_native_image_sizes(
    make_file: FileFactory, output_dir: Path
) -> None:
    """A larger sample with the same pixel-noise distribution retains the same sigma units."""
    rng = np.random.default_rng(418)
    values = [
        _quality(
            Image.fromarray(np.clip(rng.normal(128, 18, (side, side, 3)), 0, 255).astype(np.uint8)),
            make_file,
            output_dir,
        )
        for side in (256, 1024)
    ]
    assert values[0].noise_sigma == pytest.approx(values[1].noise_sigma, rel=0.05)


def test_thresholds_change_failures_without_changing_recorded_signals(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Permit explicit domain thresholds while preserving the measured evidence."""
    image = _board((64, 48), contrast=6)
    strict = _quality(image, make_file, output_dir)
    permissive = _quality(
        image,
        make_file,
        output_dir,
        {"min_color_stddev": 1.0, "min_resolution": 16, "blur_threshold": 0.0},
    )
    assert strict.color_stddev == permissive.color_stddev
    assert strict.checks.solid_color.failed is True
    assert permissive.checks.solid_color.failed is False
    assert permissive.checks.resolution.failed is False
    assert permissive.checks.blur.score == 100


@pytest.mark.parametrize(
    "params",
    [
        {"max_noise_sigma": 0.0},
        {"min_color_stddev": -1.0},
        {"max_clipped_fraction": 1.1},
        {"analysis_size": 4},
        {"max_noise_sigma": float("nan")},
        {"undeclared": True},
    ],
)
def test_parameters_reject_invalid_thresholds_and_unknown_fields(
    params: dict[str, JsonValue],
) -> None:
    """Reject invalid configuration before reading image data."""
    with pytest.raises(SchemaValidationError):
        ImageQualityParams.model_validate(params)


def test_exif_orientation_sets_corrected_dimensions(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Use displayed-pixel coordinates after camera orientation correction."""
    encoded = BytesIO()
    exif = Image.Exif()
    exif[274] = 6
    _board((80, 24)).save(encoded, format="JPEG", exif=exif)
    source = make_file(encoded.getvalue(), "oriented.jpg", "image")
    result = REGISTRY["image.quality"].run([source], output_dir)
    quality = ImageQualityMeasurement.model_validate(result.files[0].metadata["image_quality"])
    assert (quality.width, quality.height) == (24, 80)


def test_fully_transparent_pixels_are_scored_as_visible_blank_image(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Hidden color detail must not make a transparent image appear usable."""
    pixels = np.dstack([np.asarray(_board()), np.zeros((384, 512), dtype=np.uint8)])
    quality = _quality(Image.fromarray(pixels), make_file, output_dir)
    assert quality.checks.solid_color.failed is True
    assert quality.score == 0


def test_determinism_metadata_immutability_and_complete_failure_evidence(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Keep source identity and legacy evidence while reporting every new failed check."""
    encoded = BytesIO()
    Image.new("RGB", (8, 8), "black").save(encoded, format="PNG")
    source = make_file(encoded.getvalue(), "blank.png", "image")
    source.metadata["custom"] = {"labels": ["generated"]}
    before = source.model_dump(mode="json")
    first = REGISTRY["image.quality"].run([source], output_dir)
    second = REGISTRY["image.quality"].run([source], output_dir)
    assert first == second
    assert source.model_dump(mode="json") == before
    assert first.files[0].id == source.id
    assert first.files[0].metadata["custom"] == source.metadata["custom"]
    quality = ImageQualityMeasurement.model_validate(first.files[0].metadata["image_quality"])
    assert set(quality.scores) == {"blur", "exposure", "noise", "resolution", "solid_color"}
    assert all(0 <= score <= 100 for score in quality.scores.values())
    assert set(quality.issues) == {"blurry", "brightness", "low_resolution"}
    assert {value["code"] for value in first.quality["issues"]} == {
        "blurry",
        "brightness",
        "low_resolution",
        "solid_color",
    }
    assert all(value["reason"] for value in first.quality["issues"])


def test_single_pixel_and_empty_inputs_remain_bounded(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Handle degenerate dimensions without undefined high-frequency statistics."""
    quality = _quality(Image.new("RGB", (1, 1), "gray"), make_file, output_dir)
    assert quality.noise_sigma == 0
    assert quality.blur_variance == 0
    assert REGISTRY["image.quality"].run([], output_dir).quality["measurements"] == {}
