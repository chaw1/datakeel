# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Regenerate real development artifacts from explicit local inputs, with no network API."""

from __future__ import annotations

import argparse
import base64
from io import BytesIO
from pathlib import Path

import PIL
from PIL import Image, ImageOps

from scripts.we_e1.generate import ROOT, canonical
from scripts.we_e1.isolation import split_assets, split_overlap
from scripts.we_e1.models import Boundary, EvidenceFile, PublicRow
from scripts.we_e1.preprocess import prepare_image, sha256
from scripts.we_e1.public_inputs import (
    COMMONS_CANDIDATES,
    COMMONS_JPG,
    COMMONS_RAW,
    evidence,
    local_bytes,
)
from scripts.we_e1.public_models import LicenseLedger, PublicAsset, PublicManifest
from scripts.we_e1.public_sources import build_sources


class PublicBuild(Boundary):
    """Keep public small artifacts separate from retained internal original/variant bytes."""

    public_files: dict[str, bytes]
    retained_files: dict[str, bytes]


def _variants(original: bytes, *, text: bool) -> tuple[tuple[str, bytes], ...]:
    if text:
        return (("spacing-v1", original + b"  "),)
    prepared = base64.b64decode(prepare_image(original).payload_base64, validate=True)
    with Image.open(BytesIO(prepared)) as image:
        output = BytesIO()
        ImageOps.mirror(image).save(output, format="PNG", compress_level=9)
    return (("prepared-png-v1", prepared), ("mirror-png-v1", output.getvalue()))


def _assets(
    root: Path, rows: tuple[PublicRow, ...], files: dict[str, bytes], ledger: LicenseLedger
) -> tuple[PublicAsset, ...]:
    assets: list[PublicAsset] = []
    eligible = {item.stable_id: item.eligible for item in ledger.records}
    for index, row in enumerate(rows):
        text = row.stable_id.startswith("hf:")
        original = files.get(row.original_file.path)
        if original is None:
            original = local_bytes(root, row.original_file.path)
        contents = [("original", row.original_file)]
        for variant, content in _variants(original, text=text):
            prefix = f"variant-{index}" if text else "commons-152924098"
            name = f"derived/{prefix}-{variant}.bytes"
            files[name] = content
            contents.append((variant, EvidenceFile(path=name, sha256=sha256(content))))
        for variant, content_file in contents:
            assets.append(
                PublicAsset(
                    asset_id=f"public-{index:02d}-{variant}",
                    modality="text" if text else "image",
                    stable_source_id=row.stable_id,
                    original_group=row.semantic_group,
                    near_duplicate_cluster=row.near_duplicate_cluster,
                    transformation_family=row.transformation_family,
                    variant=variant,
                    original_sha256=row.original_sha256,
                    content_sha256=content_file.sha256,
                    content=content_file,
                    license_eligible=eligible[row.stable_id],
                )
            )
    return split_assets(tuple(assets))


def build_public(root: Path) -> PublicBuild:
    """Hash original responses and actual transformations; never read any held-out inputs."""
    bundle = build_sources(root)
    files = dict(bundle.files)
    registry = canonical(bundle.registry.model_dump(mode="json"))
    ledger = canonical(bundle.ledger.model_dump(mode="json"))
    rows = tuple(row for source in bundle.registry.sources for row in source.rows)
    assets = _assets(root, rows, files, bundle.ledger)
    if split_overlap(assets) or {a.split for a in assets} != {"dev_tune", "dev_validation"}:
        msg = "public development groups intersect or a partition is empty"
        raise ValueError(msg)
    manifest = PublicManifest(
        pillow_version=PIL.__version__,
        sources_registry_sha256=sha256(registry),
        license_ledger_sha256=sha256(ledger),
        raw_inputs=tuple(
            evidence(root, name)
            for name in (
                "proxy-hf/wiki40b-api.json",
                "proxy-hf/wiki40b-card.md",
                "proxy-hf/en-train-0-4.json",
                "proxy-hf/zh-cn-train-0-4.json",
                "proxy-hf/wikipedia-copyrights.html",
                "proxy-hf/cc-by-sa-4.0.html",
                COMMONS_CANDIDATES,
                COMMONS_RAW,
                COMMONS_JPG,
            )
        ),
        assets=assets,
    )
    public = {
        "sources.json": registry,
        "public-manifest.json": canonical(manifest.model_dump(mode="json")),
        "license-ledger.json": ledger,
    }
    public["public-hashes.json"] = canonical(
        {name: sha256(data) for name, data in sorted(public.items())}
    )
    return PublicBuild(public_files=public, retained_files=files)


def write_public(build: PublicBuild, root: Path, out: Path, *, check: bool) -> None:
    """Write or check only our declared generated files, preserving downloaded bytes."""
    for base, files in ((root, build.retained_files), (out, build.public_files)):
        for name, data in files.items():
            target = base / name
            if not target.resolve().is_relative_to(base.resolve()) or any(
                p.is_symlink() for p in (target, *target.parents)
            ):
                msg = "public output escaped root or used symlink"
                raise ValueError(msg)
            if check:
                if not target.is_file() or target.read_bytes() != data:
                    msg = f"public frozen bytes differ: {name}"
                    raise ValueError(msg)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)


def main() -> None:
    """Generate/check selected public development data offline, with an explicit root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-root", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=ROOT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    write_public(
        build_public(args.development_root), args.development_root, args.out, check=args.check
    )


if __name__ == "__main__":
    main()
