# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""E1 byte-contract parity and entirely local fake execution."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest
from PIL import Image, PngImagePlugin

from datakeel.core.models import FileItem
from datakeel.core.vector_models import EmbedParams
from datakeel.evidence.vector_payload import prepare_wire
from datakeel.evidence.vector_transport import FakeVectorTransport
from scripts.we_e1.preprocess import prepare_image, prepare_text
from tests.evidence.vector_helpers import vector_dataset, vector_prepare, vector_run

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


@pytest.mark.parametrize("text", ["e\u0301\n exact ", "é", "plain\r\ntext"])
def test_runtime_preserves_exact_e1_utf8_and_final_serialized_bytes(
    tmp_path: Path, text: str
) -> None:
    """Original UTF-8 bytes remain unchanged, including combining characters and whitespace."""
    path = tmp_path / "source.txt"
    raw = text.encode()
    path.write_bytes(raw)
    wire = prepare_wire(
        FileItem(
            path=str(path),
            filename=path.name,
            sha256=hashlib.sha256(raw).hexdigest(),
            modality="text",
        ),
        EmbedParams(),
    )
    frozen = prepare_text(text, tokenizer="fake-codepoint-v1")
    assert frozen.payload_sha256 == wire.frozen.payload_hash
    assert json.loads(wire.body)["input"] == [text]
    assert hashlib.sha256(wire.body).hexdigest() == wire.frozen.body_hash


def test_runtime_image_preprocessing_matches_e1_frozen_bytes(tmp_path: Path) -> None:
    """EXIF/RGB/PNG512 output retains the E1 byte-level preprocessing contract."""
    path = tmp_path / "source.png"
    Image.new("RGB", (700, 300), "blue").save(path)
    raw = path.read_bytes()
    params = EmbedParams(modality="image", dimensions=1024)
    wire = prepare_wire(
        FileItem(
            path=str(path),
            filename=path.name,
            sha256=hashlib.sha256(raw).hexdigest(),
            modality="image",
        ),
        params,
    )
    assert wire.frozen.payload_hash == prepare_image(raw).payload_sha256
    assert json.loads(wire.body)["input"][0]["image"] == prepare_image(raw).data_uri


def test_equal_preprocessed_images_still_bind_distinct_original_revisions(tmp_path: Path) -> None:
    """Removed metadata cannot preserve an embedding key or anchor for different original bytes."""
    image = Image.new("RGB", (20, 20), "blue")
    original = tmp_path / "original.png"
    changed = tmp_path / "changed.png"
    image.save(original)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("description", "generated metadata variant")
    image.save(changed, pnginfo=metadata)
    params = EmbedParams(modality="image", dimensions=1024)
    wires = [
        prepare_wire(
            FileItem(
                path=str(path),
                filename=path.name,
                modality="image",
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            ),
            params,
        )
        for path in (original, changed)
    ]
    assert wires[0].frozen.body_hash == wires[1].frozen.body_hash
    assert wires[0].frozen.payload_hash == wires[1].frozen.payload_hash
    assert wires[0].frozen.cache_key != wires[1].frozen.cache_key


def test_prepare_constructs_no_transport_and_fake_execution_opens_no_network(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offline_network: None
) -> None:
    """Preparation and fake execution need no external network or provider backend."""

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("unexpected transport construction or network access")

    dataset = vector_dataset(db, tmp_path / "inputs")
    with monkeypatch.context() as scoped:
        scoped.setattr(FakeVectorTransport, "__init__", forbidden)
        assert vector_prepare(db, dataset).requires_approval
    assert vector_run(db, dataset).state == "COMPLETED"
