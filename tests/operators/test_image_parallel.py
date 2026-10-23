# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Ordered image concurrency keeps serial pixels, metadata and resource boundaries."""

from __future__ import annotations

import struct
import zlib
from io import BytesIO
from pathlib import Path
from threading import Barrier, Lock, get_ident
from typing import TYPE_CHECKING

import numpy as np
import pytest
from PIL import Image

from datakeel.operators import REGISTRY
from datakeel.operators.image import helpers, parallel
from datakeel.operators.image.limits import ImageResourceLimit

if TYPE_CHECKING:
    from datakeel.core.models import FileItem
    from tests.operators.factories import FileFactory, ImageFactory


def _varied_images(make_file: FileFactory) -> list[FileItem]:
    files: list[FileItem] = []
    for mode in ("RGB", "RGBA", "L", "P"):
        image = Image.new(mode, (31, 17))
        if mode == "P":
            image.putpalette([255, 0, 0, 0, 255, 0] + [0] * 762)
            image.putpixel((0, 0), 1)
            image.info["transparency"] = 0
        else:
            image.paste("white", (5, 2, 20, 11))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        files.append(make_file(buffer.getvalue(), f"{mode}.png", "image"))
    oriented = Image.new("RGB", (30, 16), "red")
    orientation = Image.Exif()
    orientation[274] = 6
    buffer = BytesIO()
    oriented.save(buffer, format="JPEG", exif=orientation)
    files.append(make_file(buffer.getvalue(), "camera.jpg", "image"))
    return [
        file.model_copy(update={"metadata": {"retained": {"values": [1, 2]}, "width": -1}})
        for file in files
    ]


@pytest.mark.parametrize(
    ("name", "params"),
    [
        ("image.resize", {"width": 40, "height": 28}),
        ("image.resize", {"width": 40, "height": 28, "preserve_aspect": False}),
        ("image.thumbnail", {"size": 12}),
        ("image.thumbnail", {"size": 64}),
        ("image.convert", {"format": "png"}),
        ("image.convert", {"format": "jpg", "quality": 71}),
        ("image.convert", {"format": "webp", "quality": 71}),
    ],
)
def test_parallel_images_match_serial_bytes_pixels_and_metadata(
    make_file: FileFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    params: dict[str, str | int | bool],
) -> None:
    """Keep transparency, camera orientation, output ordering and inherited facts."""
    files = _varied_images(make_file)
    original = [file.model_dump(mode="json") for file in files]
    with monkeypatch.context() as serial_mode:
        serial_mode.setattr(parallel, "MAX_PARALLEL_PIXELS", 0)
        serial = REGISTRY[name].run(files, tmp_path / "serial", params)
    concurrent = REGISTRY[name].run(files, tmp_path / "parallel", params)
    assert concurrent.quality == serial.quality
    assert [file.metadata["source_file_id"] for file in concurrent.files] == [f.id for f in files]
    for expected, actual in zip(serial.files, concurrent.files, strict=True):
        assert Path(actual.path).read_bytes() == Path(expected.path).read_bytes()
        assert actual.model_dump(exclude={"id", "path"}) == expected.model_dump(
            exclude={"id", "path"}
        )
        with Image.open(actual.path) as actual_image, Image.open(expected.path) as expected_image:
            np.testing.assert_array_equal(np.asarray(actual_image), np.asarray(expected_image))
    assert [file.model_dump(mode="json") for file in files] == original


def test_small_image_batch_uses_at_most_four_workers_in_source_order(
    make_image: ImageFactory,
) -> None:
    """Exercise real overlap while returning files in their original list order."""
    files = [make_image(value=index) for index in range(8)]
    barrier, lock = Barrier(4), Lock()
    threads: set[int] = set()

    def transform(file: FileItem) -> FileItem:
        with lock:
            threads.add(get_ident())
        barrier.wait(timeout=5)
        return file

    assert parallel.map_images(files, transform) == files
    assert len(threads) == 4
    assert get_ident() not in threads


@pytest.mark.parametrize("condition", ["large_input", "large_output", "encoded_size", "single"])
def test_memory_sensitive_batches_use_serial_execution(
    make_image: ImageFactory, monkeypatch: pytest.MonkeyPatch, condition: str
) -> None:
    """Use actual image headers and requested output bounds instead of manifest dimensions."""
    files = [make_image(), make_image()]
    if condition == "large_input":
        files.append(make_image(width=1001, height=1000))
    if condition == "encoded_size":
        monkeypatch.setattr(parallel, "MAX_IMAGE_BYTES", 1)
    if condition == "single":
        files = files[:1]
    threads: set[int] = set()

    def transform(file: FileItem) -> FileItem:
        threads.add(get_ident())
        return file

    output_pixels = 1_000_001 if condition == "large_output" else 0
    assert parallel.map_images(files, transform, output_pixels) == files
    assert threads == {get_ident()}


def test_parallel_transform_exception_propagates_and_joins_workers(
    make_image: ImageFactory,
) -> None:
    """Surface worker errors to the pipeline caller without detached transformations."""
    files = [make_image(), make_image()]
    completed: list[str] = []
    barrier = Barrier(2)

    def transform(file: FileItem) -> FileItem:
        barrier.wait(timeout=5)
        if file.id == files[0].id:
            msg = "conversion failed"
            raise OSError(msg)
        completed.append(file.id)
        return file

    with pytest.raises(OSError, match="conversion failed"):
        parallel.map_images(files, transform)
    assert completed == [files[1].id]


@pytest.mark.parametrize("name", ["image.resize", "image.thumbnail", "image.convert"])
def test_batch_decoding_retains_resource_limits_and_corrupt_errors(
    make_image: ImageFactory,
    make_file: FileFactory,
    output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    """Retain original decoder safeguards and exception types in batch operations."""
    valid = make_image()
    broken = make_file(b"invalid image", "broken.png", "image")
    with pytest.raises(OSError, match="cannot identify image"):
        REGISTRY[name].run([valid, broken], output_dir)
    with monkeypatch.context() as small_limit:
        small_limit.setattr(helpers, "MAX_IMAGE_BYTES", 1)
        with pytest.raises(ImageResourceLimit, match="bytes"):
            REGISTRY[name].run([valid, valid], output_dir)
    assert REGISTRY[name].run([], output_dir).files == []


def test_batch_rejects_oversized_header_before_decoding(
    make_image: ImageFactory, output_dir: Path
) -> None:
    """Keep the 16-million-pixel guard when a batch mixes small and oversized inputs."""
    valid, oversized = make_image(), make_image(width=2, height=2)
    data = bytearray(Path(oversized.path).read_bytes())
    data[16:24] = struct.pack(">II", 4001, 4000)
    data[29:33] = struct.pack(">I", zlib.crc32(data[12:29]))
    Path(oversized.path).write_bytes(data)
    with pytest.raises(ImageResourceLimit, match="pixels"):
        REGISTRY["image.resize"].run([valid, oversized], output_dir)


def test_header_bomb_falls_back_to_original_serial_error_order(
    make_image: ImageFactory, output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defer preflight decompression errors until the original decoder reaches that input."""
    valid, oversized = make_image(), make_image()
    original_open = Image.open

    def inspect(path: Path) -> Image.Image:
        if path == Path(oversized.path):
            msg = "oversized header"
            raise Image.DecompressionBombError(msg)
        return original_open(path)

    monkeypatch.setattr(Image, "open", inspect)
    with pytest.raises(Image.DecompressionBombError, match="oversized header"):
        REGISTRY["image.convert"].run([valid, oversized], output_dir)
    assert len(list(output_dir.glob("*.png"))) == 1
