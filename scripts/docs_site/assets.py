# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Copy site images/static assets and generate Open Graph social preview PNGs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont

if TYPE_CHECKING:
    from scripts.docs_site.models import SiteConfig

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_OG_WIDTH = 1200
_OG_HEIGHT = 630


def _load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    )
    for candidate in candidates:
        font_path = Path(candidate)
        if font_path.is_file():
            try:
                return ImageFont.truetype(str(font_path), size=size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _draw_logo_mark(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rounded_rectangle((x, y, x + 48, y + 48), radius=10, fill="#E2E9F4", outline="#2459A8")
    for left, top, right, bottom in ((10, 22, 18, 40), (21, 9, 29, 40), (32, 7, 40, 29)):
        draw.rounded_rectangle(
            (x + left, y + top, x + right, y + bottom),
            radius=3,
            fill="#2459A8",
        )


def _paste_preview(canvas: Image.Image, draw: ImageDraw.ImageDraw, screenshot_path: Path) -> None:
    if not screenshot_path.is_file():
        return
    with Image.open(screenshot_path) as raw:
        shot = raw.convert("RGB")
        shot.thumbnail((470, 390))
        box_x = _OG_WIDTH - 84 - shot.width
        box_y = 112
        frame = (box_x - 8, box_y - 8, box_x + shot.width + 8, box_y + shot.height + 8)
        draw.rounded_rectangle(frame, radius=10, fill="#F7F5EE", outline="#BFB8A6", width=2)
        canvas.paste(shot, (box_x, box_y))


def _build_social_card(screenshot_path: Path, destination: Path, version: str) -> None:
    canvas = Image.new("RGB", (_OG_WIDTH, _OG_HEIGHT), "#F7F5EE")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, _OG_WIDTH, 10), fill="#2459A8")
    draw.rectangle((48, 44, _OG_WIDTH - 48, _OG_HEIGHT - 44), fill="#FFFEFA", outline="#D9D4C7")
    _draw_logo_mark(draw, 84, 84)

    headline_font = _load_font(34, bold=True)
    body_font = _load_font(22)
    mono_font = _load_font(18)

    draw.text((150, 86), "Datakeel", fill="#1B1D22", font=_load_font(44, bold=True))
    draw.text((84, 166), "Local-first workbench for", fill="#1B1D22", font=headline_font)
    draw.text((84, 212), "auditable datasets & metrics", fill="#2459A8", font=headline_font)
    draw.text(
        (84, 276),
        "Visual QA  |  Traceable SQL  |  Human-Approved MCP",
        fill="#5F5C55",
        font=body_font,
    )

    pills = (
        ("Apache-2.0", "#EBF0DF", "#536A1C"),
        (f"v{version}", "#E2E9F4", "#2459A8"),
        ("Human Sign-Off", "#F9E6E2", "#C4321A"),
    )
    cursor_x = 84
    for label, bg, fg in pills:
        width = len(label) * 11 + 28
        draw.rounded_rectangle((cursor_x, 340, cursor_x + width, 378), radius=6, fill=bg)
        draw.text((cursor_x + 14, 348), label, fill=fg, font=mono_font)
        cursor_x += width + 12

    draw.text(
        (84, 518),
        "github.com/chaw1/datakeel  |  chaw1.github.io/datakeel",
        fill="#5F5C55",
        font=mono_font,
    )
    _paste_preview(canvas, draw, screenshot_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, format="PNG", optimize=True)


def copy_site_assets(config: SiteConfig) -> int:
    """Copy CSS, JS, favicon, and documentation images, then generate social preview PNGs."""
    assets_dir = config.output_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for filename in ("site.css", "site.js"):
        shutil.copy2(_STATIC_DIR / filename, assets_dir / filename)
        copied += 1

    favicon = config.repo_root / "web/public/favicon.svg"
    if favicon.is_file():
        shutil.copy2(favicon, assets_dir / "favicon.svg")
        copied += 1

    images_src = config.repo_root / "docs/images"
    images_dst = assets_dir / "images"
    if images_src.is_dir():
        for source in sorted(images_src.rglob("*")):
            if not source.is_file():
                continue
            target = images_dst / source.relative_to(images_src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1

    _build_social_card(
        config.repo_root / "docs/images/dataset-delivery-en.png",
        assets_dir / "og-en.png",
        config.version,
    )
    _build_social_card(
        config.repo_root / "docs/images/dataset-delivery-zh.png",
        assets_dir / "og-zh.png",
        config.version,
    )
    return copied + 2
