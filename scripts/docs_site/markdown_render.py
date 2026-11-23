# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Render repository Markdown documents into link-rewritten HTML with heading anchors."""

from __future__ import annotations

import html
import posixpath
import re
from typing import TYPE_CHECKING

from markdown_it import MarkdownIt

from scripts.docs_site.models import DocEntry, HeadingItem, RenderedDoc, SiteConfig

if TYPE_CHECKING:
    from pathlib import Path

_HEADING_HTML_RE = re.compile(r"<h([1-4])>(.*?)</h\1>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href="([^"]+)"')
_SRC_RE = re.compile(r'src="([^"]+)"')
_NON_SLUG_RE = re.compile(r"[^\w\u4e00-\u9fff\-\s]")
_SPACE_RE = re.compile(r"\s+")


def slugify_heading(raw_text: str, counts: dict[str, int]) -> str:
    """Create a stable GitHub-style heading anchor slug with duplicate disambiguation."""
    plain = html.unescape(_TAG_RE.sub("", raw_text)).strip().lower()
    cleaned = _NON_SLUG_RE.sub("", plain)
    slug = _SPACE_RE.sub("-", cleaned).strip("-") or "section"
    seen = counts.get(slug, 0)
    counts[slug] = seen + 1
    return slug if seen == 0 else f"{slug}-{seen}"


def _resolve_repo_relative(source_rel: str, target_path: str) -> str:
    base_dir = posixpath.dirname(source_rel)
    joined = posixpath.join(base_dir, target_path) if base_dir else target_path
    return posixpath.normpath(joined)


def _rewrite_href(
    raw_href: str,
    source_rel: str,
    doc_url_map: dict[str, str],
    config: SiteConfig,
) -> str:
    if raw_href.startswith(("#", "http://", "https://", "mailto:")):
        return raw_href
    path_part, _, fragment = raw_href.partition("#")
    anchor = f"#{fragment}" if fragment else ""
    if not path_part:
        return anchor or raw_href
    resolved = _resolve_repo_relative(source_rel, path_part)
    static_targets = {"README.md": "", "README.zh.md": "zh/"}
    if resolved in static_targets:
        result = f"{config.href(static_targets[resolved])}{anchor}"
    elif resolved in doc_url_map:
        result = f"{config.href(doc_url_map[resolved])}{anchor}"
    elif resolved.startswith("docs/images/"):
        rel_img = resolved.removeprefix("docs/images/")
        result = config.href(f"assets/images/{rel_img}")
    else:
        result = f"{config.repo_url}/blob/main/{resolved}{anchor}"
    return result


def _rewrite_src(raw_src: str, source_rel: str, config: SiteConfig) -> str:
    if raw_src.startswith(("http://", "https://", "data:")):
        return raw_src
    resolved = _resolve_repo_relative(source_rel, raw_src)
    if resolved.startswith("docs/images/"):
        rel_img = resolved.removeprefix("docs/images/")
        return config.href(f"assets/images/{rel_img}")
    if resolved == "web/public/favicon.svg":
        return config.href("assets/favicon.svg")
    return f"{config.repo_url}/raw/main/{resolved}"


def _inject_heading_anchors(rendered: str) -> tuple[str, tuple[HeadingItem, ...]]:
    counts: dict[str, int] = {}
    headings: list[HeadingItem] = []

    def replace(match: re.Match[str]) -> str:
        level = int(match.group(1))
        inner = match.group(2)
        slug = slugify_heading(inner, counts)
        plain = html.unescape(_TAG_RE.sub("", inner)).strip()
        if level in {2, 3}:
            headings.append(HeadingItem(level=level, slug=slug, text=plain))
        return f'<h{level} id="{html.escape(slug, quote=True)}">{inner}</h{level}>'

    updated = _HEADING_HTML_RE.sub(replace, rendered)
    return updated, tuple(headings)


def render_document(
    entry: DocEntry,
    repo_root: Path,
    doc_url_map: dict[str, str],
    config: SiteConfig,
) -> RenderedDoc:
    """Convert one Markdown document to HTML with rewritten links and TOC anchors."""
    markdown = MarkdownIt("commonmark", {"html": True, "linkify": False}).enable(
        ["table", "strikethrough"]
    )
    source_text = (repo_root / entry.source_rel).read_text(encoding="utf-8")
    raw_html = markdown.render(source_text)
    anchored_html, headings = _inject_heading_anchors(raw_html)

    def _href_sub(match: re.Match[str]) -> str:
        rewritten = _rewrite_href(match.group(1), entry.source_rel, doc_url_map, config)
        return f'href="{html.escape(rewritten, quote=True)}"'

    def _src_sub(match: re.Match[str]) -> str:
        rewritten = _rewrite_src(match.group(1), entry.source_rel, config)
        return f'src="{html.escape(rewritten, quote=True)}" loading="lazy"'

    body_html = _SRC_RE.sub(_src_sub, _HREF_RE.sub(_href_sub, anchored_html))
    return RenderedDoc(entry=entry, body_html=body_html, headings=headings)
