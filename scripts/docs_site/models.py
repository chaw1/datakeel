# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed models for the static documentation site builder."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from datakeel.core.models import BoundaryModel

LanguageCode = Literal["en", "zh"]


class SiteConfig(BoundaryModel):
    """Configuration for generating the static documentation site."""

    repo_root: Path
    output_dir: Path
    base_url: str = "https://datakeel.jiawis.com/"
    repo_url: str = "https://github.com/chaw1/datakeel"
    version: str = "0.27.1"

    @property
    def normalized_base_url(self) -> str:
        """Return the base URL with a single trailing slash."""
        return self.base_url.rstrip("/") + "/"

    @property
    def base_path(self) -> str:
        """Return the URL path prefix (for example `/datakeel/` or `/`)."""
        parsed = urlparse(self.normalized_base_url)
        path = parsed.path or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path.rstrip("/") + "/"

    def absolute_url(self, rel_path: str) -> str:
        """Join a site-relative path onto the canonical base URL."""
        cleaned = rel_path.lstrip("/")
        return f"{self.normalized_base_url}{cleaned}"

    def href(self, rel_path: str) -> str:
        """Join a site-relative path onto the site path prefix."""
        cleaned = rel_path.lstrip("/")
        return f"{self.base_path}{cleaned}"


class HeadingItem(BoundaryModel):
    """One table-of-contents heading extracted from a Markdown document."""

    level: int
    slug: str
    text: str


class DocEntry(BoundaryModel):
    """Metadata and routing information for one Markdown documentation page."""

    source_rel: str
    url_path: str
    title: str
    description: str
    lang: LanguageCode
    section_id: str
    section_en: str
    section_zh: str
    alternate_url: str | None = None
    order: int = 0
    lastmod: str | None = None


class RenderedDoc(BoundaryModel):
    """Rendered HTML body and extracted headings for one documentation page."""

    entry: DocEntry
    body_html: str
    headings: tuple[HeadingItem, ...]


class PageMeta(BoundaryModel):
    """Per-page SEO, hreflang, navigation, and structured-data metadata."""

    lang: LanguageCode
    title: str
    description: str
    url_path: str
    alternate_url: str | None = None
    switch_href: str
    json_ld_blocks: tuple[dict[str, object], ...] = ()
    is_docs: bool = False


class FaqItem(BoundaryModel):
    """One question-and-answer pair rendered in HTML and FAQPage JSON-LD."""

    question: str
    answer: str


class PillarItem(BoundaryModel):
    """One landing-page capability pillar."""

    index: str
    eyebrow: str
    title: str
    summary: str
    bullets: tuple[str, ...]
    doc_href: str
    doc_label: str


class ComparisonRow(BoundaryModel):
    """One row in the honest positioning comparison table."""

    capability: str
    datakeel: str
    single_purpose: str


class LocalizedLanding(BoundaryModel):
    """Complete localized copy, pillars, comparison rows, and FAQs for one language."""

    page_title: str
    meta_desc: str
    h1: str
    lead: str
    cta_docs: str
    cta_tour: str
    cta_github: str
    qs_bar: str
    copy_label: str
    copied_label: str
    hero_caption: str
    pillars_kicker: str
    pillars_h2: str
    pillars_lead: str
    visual_kicker: str
    visual_h2: str
    visual_cap1: str
    visual_cap2: str
    compare_kicker: str
    compare_h2: str
    compare_lead: str
    th_cap: str
    th_dk: str
    th_other: str
    docs_kicker: str
    docs_h2: str
    faq_kicker: str
    faq_h2: str
    hero_img: str
    evidence_img: str
    docs_href: str
    tour_href: str
    url_path: str
    alt_url: str
    pillars: tuple[PillarItem, ...]
    comparison: tuple[ComparisonRow, ...]
    faq: tuple[FaqItem, ...]


class LandingBundle(BoundaryModel):
    """Bilingual landing-page content loaded from static/landing.yaml."""

    en: LocalizedLanding
    zh: LocalizedLanding


class BuildSummary(BoundaryModel):
    """Summary counters produced by a static site build."""

    pages_written: int
    docs_written: int
    assets_copied: int
    sitemap_urls: int
