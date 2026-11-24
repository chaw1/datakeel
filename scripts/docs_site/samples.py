# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate the deterministic 3-image train/test leakage sample archive."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

SAMPLE_ARCHIVE_REL = "docs/samples/warehouse-leakage-sample.zip"
SAMPLE_ROOT_NAME = "warehouse-leakage-sample"
_ZIP_EPOCH = (2026, 1, 1, 0, 0, 0)
_FILE_MODE = 0o644 << 16

_FIXTURE_SPECS: tuple[tuple[str, str, str, tuple[int, int, int, int]], ...] = (
    ("train", "loading-bay", "pallet", (76, 125, 107, 53)),
    ("test", "loading-bay-copy", "pallet", (76, 125, 107, 53)),
    ("test", "entrance", "forklift", (148, 65, 114, 98)),
)


def _draw_pallet_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(((14, 60), (207, 40), (305, 61), (305, 147), (14, 163)), fill="#a6b8bd")
    draw.polygon(((14, 60), (207, 40), (305, 61), (14, 73)), fill="#365365")
    draw.rectangle((40, 82, 133, 159), fill="#263e49")
    draw.rectangle((47, 88, 126, 125), fill="#6d8993")
    for y in range(93, 121, 8):
        draw.line((47, y, 126, y), fill="#abc1c5", width=2)
    draw.rectangle((161, 78, 248, 142), fill="#eff0e6")
    draw.rectangle((170, 86, 205, 119), fill="#4a7280")
    draw.rectangle((211, 86, 239, 119), fill="#4a7280")
    draw.rectangle((76, 154, 183, 178), fill="#724b2a")
    for x, y in ((79, 129), (115, 125), (149, 133)):
        draw.rectangle((x, y, x + 30, 155), fill="#cf9a60", outline="#9e6c40", width=2)
        draw.line((x + 15, y, x + 15, 154), fill="#eac58c", width=3)
    draw.line((198, 184, 294, 172), fill="#f6edcb", width=5)


def _draw_forklift_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(((0, 94), (104, 51), (104, 148), (0, 166)), fill="#7c927b")
    draw.polygon(((116, 150), (251, 84), (320, 99), (320, 203)), fill="#788585")
    draw.line((193, 174, 316, 124), fill="#ece6ae", width=5)
    draw.rectangle((148, 97, 220, 151), fill="#ba812d")
    draw.rectangle((160, 65, 205, 108), outline="#233737", width=6)
    draw.rectangle((213, 80, 224, 155), fill="#263b3f")
    draw.line((223, 155, 261, 155), fill="#263b3f", width=6)
    for x in (149, 195):
        draw.ellipse((x, 137, x + 24, 162), fill="#283f43")


def _render_scene_png(label: str) -> bytes:
    image = Image.new("RGB", (320, 210), "#dce7e9")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 141, 320, 210), fill="#c6c3ad")
    if label == "pallet":
        _draw_pallet_scene(draw)
    else:
        _draw_forklift_scene(draw)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def sample_archive_entries() -> tuple[tuple[str, bytes], ...]:
    """Return sorted (archive_path, payload_bytes) entries for the 3-image leakage fixture."""
    entries: list[tuple[str, bytes]] = []
    for split, name, label, bbox in _FIXTURE_SPECS:
        prefix = f"{SAMPLE_ROOT_NAME}/{split}/{name}"
        entries.append((f"{prefix}/image.png", _render_scene_png(label)))
        annotation = {
            "width": 320,
            "height": 210,
            "annotations": [{"category": label, "bbox": list(bbox)}],
        }
        entries.append(
            (
                f"{prefix}/annotations.json",
                (json.dumps(annotation, indent=2) + "\n").encode("utf-8"),
            )
        )
        if label == "pallet":
            entries.append(
                (
                    f"{prefix}/caption.txt",
                    f"Generated warehouse sample: {label}\n".encode(),
                )
            )
    entries.sort(key=lambda item: item[0])
    return tuple(entries)


def build_warehouse_sample_zip_bytes() -> bytes:
    """Build deterministic ZIP bytes matching the documented 3-image leakage walkthrough."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for rel_path, payload in sample_archive_entries():
            info = zipfile.ZipInfo(filename=rel_path, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = _FILE_MODE
            archive.writestr(info, payload)
    return buffer.getvalue()


def write_warehouse_sample_zip(destination: Path) -> Path:
    """Write the deterministic 3-image sample archive to destination."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(build_warehouse_sample_zip_bytes())
    return destination


def main() -> None:
    """Regenerate docs/samples/warehouse-leakage-sample.zip in the repository."""
    repo_root = Path(__file__).resolve().parents[2]
    write_warehouse_sample_zip(repo_root / SAMPLE_ARCHIVE_REL)


if __name__ == "__main__":
    main()
