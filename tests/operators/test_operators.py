# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for operators."""

from __future__ import annotations

import json
import struct
import zlib
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import jsonschema
import pytest
from PIL import Image, PngImagePlugin

from datakeel.operators import REGISTRY, manifests
from datakeel.operators.image import helpers
from datakeel.operators.image.helpers import decode
from datakeel.operators.image.limits import ImageResourceLimit
from datakeel.quality import score_quality

if TYPE_CHECKING:
    from typing import Never

    from tests.operators.factories import FileFactory, ImageFactory


def test_file_dedup_uses_real_content(make_file: FileFactory, output_dir: Path) -> None:
    """Verify file dedup uses real content."""
    first = make_file("same")
    second = make_file("same")
    third = make_file("different")
    first = first.model_copy(update={"sha256": "untrusted"})
    third = third.model_copy(update={"sha256": "untrusted"})
    result = REGISTRY["file.dedup"].run([first, second, third], output_dir)
    assert [file.id for file in result.files] == [first.id, third.id]
    assert len({file.sha256 for file in result.files}) == 2
    assert result.quality["removed_count"] == 1


def test_corrupt_check_decodes_images(
    make_image: ImageFactory, make_file: FileFactory, output_dir: Path
) -> None:
    """Verify corrupt check decodes images."""
    valid = make_image()
    broken = make_file(b"not an image", "broken.png", "image")
    result = REGISTRY["file.corrupt_check"].run([valid, broken], output_dir)
    assert len(result.files) == 1
    assert result.files[0].metadata["corrupt"] is False
    assert result.quality["issues"][0]["code"] == "corrupt"
    marked = REGISTRY["file.corrupt_check"].run([broken], output_dir, {"remove": False})
    assert marked.files[0].metadata["corrupt"] is True


def test_empty_check_whitespace(make_file: FileFactory, output_dir: Path) -> None:
    """Verify empty check whitespace."""
    files = [make_file(""), make_file(" \n\t"), make_file("content")]
    result = REGISTRY["file.empty_check"].run(files, output_dir)
    assert [file.id for file in result.files] == [files[2].id]
    marked = REGISTRY["file.empty_check"].run(files, output_dir, {"remove": False})
    assert [file.metadata["empty"] for file in marked.files] == [True, True, False]


def test_image_quality_detects_issues(make_image: ImageFactory, output_dir: Path) -> None:
    """Verify image quality detects issues."""
    result = REGISTRY["image.quality"].run([make_image(width=20, height=10, value=0)], output_dir)
    quality = result.files[0].metadata["image_quality"]
    assert (quality["width"], quality["height"]) == (20, 10)
    assert quality["brightness"] == quality["blur_variance"] == 0
    assert set(quality["issues"]) == {"brightness", "low_resolution"}
    assert "exposure failed" in quality["checks"]["blur"]["reason"]


def test_resize_preserves_aspect_and_original(make_image: ImageFactory, output_dir: Path) -> None:
    """Verify resize preserves aspect and original."""
    source = make_image()
    original = Path(source.path).read_bytes()
    result = REGISTRY["image.resize"].run([source], output_dir, {"width": 60, "height": 60})
    with Image.open(result.files[0].path) as image:
        assert image.size == (60, 30)
    assert Path(source.path).read_bytes() == original
    assert result.files[0].id != source.id
    assert result.files[0].metadata["source_file_id"] == source.id


def test_thumbnail_never_upscales(make_image: ImageFactory, output_dir: Path) -> None:
    """Verify thumbnail never upscales."""
    large = make_image()
    small = make_image(width=12, height=6)
    result = REGISTRY["image.thumbnail"].run([large, small], output_dir, {"size": 40})
    assert [Image.open(file.path).size for file in result.files] == [(40, 20), (12, 6)]
    assert all(file.metadata["usage_role"] == "preview" for file in result.files)


def test_convert_changes_real_encoding(make_image: ImageFactory, output_dir: Path) -> None:
    """Verify convert changes real encoding."""
    result = REGISTRY["image.convert"].run([make_image(channels=4)], output_dir, {"format": "jpg"})
    assert Path(result.files[0].path).read_bytes().startswith(b"\xff\xd8")
    with Image.open(result.files[0].path) as image:
        assert image.size == (160, 80)
        assert image.mode == "RGB"
    assert result.files[0].filename.endswith(".jpg")


def test_encoding_fix_normalizes_legacy_and_bom(make_file: FileFactory, output_dir: Path) -> None:
    """Verify encoding fix normalizes legacy and bom."""
    files = [make_file("caf\xe9\r\n".encode("cp1252")), make_file("你好\r\n".encode("utf-16"))]
    result = REGISTRY["text.encoding_fix"].run(files, output_dir)
    assert [Path(file.path).read_text(encoding="utf-8") for file in result.files] == [
        "café\n",
        "你好\n",
    ]
    assert [file.metadata["source_encoding"] for file in result.files] == ["cp1252", "utf-16"]


def test_pii_redact_matches_email_and_phone(make_file: FileFactory, output_dir: Path) -> None:
    """Verify pii redact matches email and phone."""
    source = make_file("Contact sample@example.org or +1 (415) 555-0132. Keep reference A42.")
    result = REGISTRY["text.pii_redact"].run([source], output_dir)
    text = Path(result.files[0].path).read_text()
    assert "example.org" not in text
    assert "415" not in text
    assert text.count("[REDACTED]") == 2
    assert "A42" in text
    assert result.quality["redactions"] == 2


def test_text_dedup_exact_and_approximate(make_file: FileFactory, output_dir: Path) -> None:
    """Verify text dedup exact and approximate."""
    files = [
        make_file("one two three four five"),
        make_file(" ONE   TWO three four five "),
        make_file("one two three four five six"),
        make_file("different subject entirely"),
    ]
    exact = REGISTRY["text.dedup"].run(files, output_dir, {"approximate": False})
    assert len(exact.files) == 3
    near = REGISTRY["text.dedup"].run(files, output_dir, {"threshold": 0.8})
    assert [file.id for file in near.files] == [files[0].id, files[3].id]


def test_text_quality_reports_unreadable_and_short(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Verify text quality reports unreadable and short."""
    result = REGISTRY["text.quality"].run([make_file("a\x01\x02")], output_dir)
    quality = result.files[0].metadata["text_quality"]
    assert quality["characters"] == 3
    assert quality["printable_ratio"] < 0.5
    assert set(quality["issues"]) == {"short_text", "non_printable"}


def test_manifest_schemas_and_validation(make_file: FileFactory, output_dir: Path) -> None:
    """Verify manifest schemas and validation."""
    assert len(manifests()) == 22
    snapshot = Path(__file__).resolve().parents[2] / "contracts/operators.json"
    assert json.loads(snapshot.read_text()) == [value.model_dump() for value in manifests()]
    for manifest in manifests():
        jsonschema.Draft202012Validator.check_schema(manifest["parameters"])
        assert manifest["inputs"]
        assert manifest["outputs"]
        assert manifest["queue"] in {"cpu", "io", "gpu"}
    with pytest.raises(ValueError, match="greater than or equal"):
        REGISTRY["image.resize"].run([], output_dir, {"width": 0})
    with pytest.raises(ValueError, match="valid integer"):
        REGISTRY["image.resize"].run([], output_dir, {"width": "100"})
    with pytest.raises(ValueError, match="Extra inputs"):
        REGISTRY["file.dedup"].run([], output_dir, {"typo": True})
    with pytest.raises(ValueError, match="requires image"):
        REGISTRY["image.resize"].run([make_file("text")], output_dir)


def test_transformed_image_metadata_matches_scoring_evidence(
    make_image: ImageFactory, output_dir: Path
) -> None:
    """Verify transformed image metadata matches scoring evidence."""
    source = make_image(width=160, height=80)
    measured = REGISTRY["image.quality"].run([source], output_dir / "measure")
    original = measured.files[0]
    original.metadata["custom"] = {"labels": ["synthetic"]}
    resized = (
        REGISTRY["image.resize"]
        .run([original], output_dir / "resize", {"width": 32, "height": 32})
        .files
    )
    thumbs = REGISTRY["image.thumbnail"].run(resized, output_dir / "thumbnail", {"size": 8}).files
    final = (
        REGISTRY["image.convert"].run(thumbs, output_dir / "convert", {"format": "jpg"}).files[0]
    )
    with Image.open(final.path) as image:
        assert image.size == (8, 4)
        assert image.format == "JPEG"
    assert final.metadata["image_quality"] == {"width": 8, "height": 4}
    assert (final.metadata["width"], final.metadata["height"], final.metadata["format"]) == (
        8,
        4,
        "jpg",
    )
    assert measured.quality["measurements"][source.id]["width"] == 160
    assert final.size == Path(final.path).stat().st_size
    assert (
        score_quality([original], {"min_image_width": 16})["dimensions"]["completeness"]["score"]
        == original.metadata["image_quality"]["overall_score"]
    )
    assert (
        score_quality([final], {"min_image_width": 16})["dimensions"]["completeness"]["score"] == 0
    )
    final.metadata["custom"]["labels"].append("changed")
    assert original.metadata["custom"]["labels"] == ["synthetic"]


@pytest.mark.parametrize("replacement", [" ", "\u3000"])
def test_text_transform_discards_old_measurements_and_refreshes_empty(
    make_file: FileFactory, output_dir: Path, replacement: str
) -> None:
    """Verify text transform discards old measurements and refreshes empty."""
    source = make_file("sample@example.org")
    measured = REGISTRY["text.quality"].run([source], output_dir / "measure")
    result = REGISTRY["text.pii_redact"].run(
        measured.files, output_dir / "redact", {"replacement": replacement}
    )
    final = result.files[0]
    assert final.metadata["empty"] is True
    assert "text_quality" not in final.metadata
    assert measured.quality["measurements"][source.id]["characters"] == len("sample@example.org")
    assert score_quality([final])["dimensions"]["completeness"]["score"] == 0


def test_image_limits_reject_headers_before_pixel_decode(
    make_image: ImageFactory, output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify image limits reject headers before pixel decode."""
    source = make_image(width=2, height=2)
    data = bytearray(Path(source.path).read_bytes())
    data[16:24] = struct.pack(">II", 4001, 4000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    Path(source.path).write_bytes(data)

    def forbidden_decode(_self: PngImagePlugin.PngImageFile) -> Never:
        """Provide the forbidden decode test fixture."""
        msg = "Oversized image reached pixel decoding"
        raise AssertionError(msg)

    monkeypatch.setattr(PngImagePlugin.PngImageFile, "load", forbidden_decode)
    with pytest.raises(ImageResourceLimit, match="pixels"):
        decode(source)
    result = REGISTRY["file.corrupt_check"].run([source], output_dir)
    assert result.files == []
    assert result.quality["issues"][0]["code"] == "image_resource_limit"
    with pytest.raises(ValueError, match="pixels"):
        REGISTRY["image.resize"].run([], output_dir, {"width": 16384, "height": 16384})


def test_image_byte_limit_applies_before_open(
    make_image: ImageFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify image byte limit applies before open."""
    source = make_image()
    monkeypatch.setattr(helpers, "MAX_IMAGE_BYTES", Path(source.path).stat().st_size - 1)
    with pytest.raises(ImageResourceLimit, match="bytes"):
        helpers.decode(source)


def test_palette_conversion_preserves_transparency(
    make_file: FileFactory, output_dir: Path
) -> None:
    """Verify palette conversion preserves transparency."""
    source_image = Image.new("P", (2, 1))
    source_image.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
    source_image.putdata([0, 1])
    buffer = BytesIO()
    source_image.save(buffer, format="PNG", transparency=0)
    source = make_file(buffer.getvalue(), "palette.png", "image")
    result = REGISTRY["image.convert"].run([source], output_dir)
    with Image.open(result.files[0].path) as converted:
        assert converted.mode == "RGBA"
        assert converted.getpixel((0, 0)) == (255, 0, 0, 0)
        assert converted.getpixel((1, 0)) == (0, 255, 0, 255)


def test_conversion_applies_camera_orientation(make_file: FileFactory, output_dir: Path) -> None:
    """Verify conversion applies camera orientation."""
    source_image = Image.new("RGB", (40, 20), "red")
    orientation = Image.Exif()
    orientation[274] = 6
    buffer = BytesIO()
    source_image.save(buffer, format="JPEG", exif=orientation)
    source = make_file(buffer.getvalue(), "camera.jpg", "image")
    final = REGISTRY["image.convert"].run([source], output_dir).files[0]
    with Image.open(final.path) as converted:
        assert converted.size == (20, 40)
    assert final.metadata["image_quality"] == {"width": 20, "height": 40}
