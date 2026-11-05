# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate tiny synthetic E1 fixtures and JSON schemas without accessing public data."""

from __future__ import annotations

import argparse
import base64
import json
from io import BytesIO
from pathlib import Path

import PIL
from PIL import Image

from scripts.we_e1.isolation import IndependentSummary, split_assets
from scripts.we_e1.models import Asset, Boundary, Manifest, RowMetadata, SearchSpace, SourceRegistry
from scripts.we_e1.preprocess import Prepared, prepare_image, prepare_text, sha256
from scripts.we_e1.protocol import ImageRequest, Response, TextRequest, WireExample
from scripts.we_e1.public_models import LicenseLedger, PublicManifest

ROOT = Path(__file__).resolve().parents[2] / "contracts" / "we-e1"


def canonical(value: object) -> bytes:
    """Encode canonical UTF-8 JSON, excluding nonfinite numeric values."""
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode()


def image_fixture(index: int, *, orientation: int = 1) -> bytes:
    """Create a non-square generated PNG with an EXIF orientation and a colored corner."""
    image = Image.new("RGB", (12 + index, 7), (index * 30, 40, 80))
    image.putpixel((0, 0), (255, 0, 0))
    exif = Image.Exif()
    exif[274] = orientation
    output = BytesIO()
    image.save(output, format="PNG", exif=exif, compress_level=9)
    return output.getvalue()


def _assets() -> tuple[Asset, ...]:
    assets: list[Asset] = []
    for index in range(8):
        group = f"authored-text-{index}"
        original = f"Contract sample {index}: cafe\u0301\n数据 {index}.".encode()
        for variant, payload in (("original", original), ("spacing", original + b"  ")):
            assets.append(_asset(group, "text", variant, original, payload))
    for index in range(4):
        group = f"authored-image-{index}"
        original = image_fixture(index)
        for variant, payload in (
            ("original", original),
            ("exif6", image_fixture(index, orientation=6)),
        ):
            assets.append(_asset(group, "image", variant, original, payload))
    return split_assets(tuple(assets))


def _asset(group: str, modality: str, variant: str, original: bytes, payload: bytes) -> Asset:
    return Asset.model_validate(
        {
            "asset_id": f"{group}-{variant}",
            "modality": modality,
            "source_kind": "synthetic_contract_only",
            "stable_source_id": f"synthetic:{group}",
            "original_group": group,
            "near_duplicate_cluster": group,
            "transformation_family": f"{group}-family",
            "variant": variant,
            "original_sha256": sha256(original),
            "content_sha256": sha256(payload),
            "content_base64": base64.b64encode(payload).decode("ascii"),
            "split": "dev_tune",
        }
    )


def _wire_examples() -> dict[str, object]:
    text = "cafe\u0301\n数据"
    text_payload = prepare_text(text, tokenizer="fake-codepoint-v1")
    image_payload = prepare_image(image_fixture(0, orientation=6))
    response = {
        "id": "fake-response-text-v1",
        "object": "list",
        "model": "text-embedding-v4",
        "data": [{"object": "embedding", "index": 0, "embedding": [1.0] + [0.0] * 63}],
        "usage": {"total_tokens": len(text)},
    }
    image_response = {
        "id": "fake-response-image-v1",
        "object": "list",
        "model": "multimodal-embedding-v1",
        "data": [{"object": "embedding", "index": 0, "embedding": [1.0] + [0.0] * 1023}],
        "usage": {"total_tokens": 100},
    }
    return {
        "mode": "fake",
        "fake_implementation_version": "we-e1-fake-v1",
        "url": "https://embedding.example.invalid/v1/embeddings",
        "method": "POST",
        "real_egress_enabled": False,
        "real_budget_cny": 0,
        "text_request": {
            "model": "text-embedding-v4",
            "input": [text],
            "dimensions": 64,
            "encoding_format": "float",
        },
        "text_prepared": text_payload.model_dump(mode="json"),
        "text_response": response,
        "image_request": {
            "model": "multimodal-embedding-v1",
            "input": [{"image": image_payload.data_uri}],
        },
        "image_prepared": image_payload.model_dump(mode="json"),
        "image_response": image_response,
        "image_compatibility": "experimental_internal_fake_only",
        "token_bound": "fake-codepoint-v1_not_provider_compatible",
    }


def build() -> dict[str, bytes]:
    """Build deterministic fixture, schema and hash artifacts in memory."""
    manifest = Manifest(
        contract_version="we-e1-v1",
        generator_version="we-e1-generator-v1",
        seed="we-e1-development-v1",
        purpose="contracts_only_not_encoder_quality",
        public_baseline_frozen=False,
        pillow_version=PIL.__version__,
        assets=_assets(),
    )
    files = {
        "manifest.json": canonical(manifest.model_dump(mode="json")),
        "fake-wire.json": canonical(_wire_examples()),
    }
    schemas: tuple[type[Boundary], ...] = (
        Manifest,
        SourceRegistry,
        SearchSpace,
        Prepared,
        TextRequest,
        ImageRequest,
        Response,
        IndependentSummary,
        WireExample,
        RowMetadata,
        PublicManifest,
        LicenseLedger,
    )
    for model in schemas:
        files[f"{model.__name__}.schema.json"] = canonical(model.model_json_schema())
    files["hashes.json"] = canonical({name: sha256(data) for name, data in sorted(files.items())})
    return files


def main() -> None:
    """Write local generated artifacts, or fail if frozen artifacts have drifted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "generated")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    files = build()
    if args.check:
        if not args.out.is_dir() or {p.name for p in args.out.iterdir()} != set(files):
            msg = "generated artifact file set differs"
            raise SystemExit(msg)
        if any((args.out / name).read_bytes() != data for name, data in files.items()):
            msg = "generated artifact bytes differ"
            raise SystemExit(msg)
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (args.out / name).write_bytes(data)


if __name__ == "__main__":
    main()
