# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate sitemap.xml, robots.txt, llms.txt, llms-full.txt, and .nojekyll."""

from __future__ import annotations

import html
from collections import defaultdict
from typing import TYPE_CHECKING

from scripts.docs_site.content import comparison_for, faq_for, pillars_for

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.docs_site.models import DocEntry, SiteConfig


def _sitemap_entry(
    loc: str,
    priority: str,
    alternates: Sequence[tuple[str, str]],
    lastmod: str | None = None,
) -> str:
    links = "".join(
        f'    <xhtml:link rel="alternate" hreflang="{lang}" '
        f'href="{html.escape(url, quote=True)}" />\n'
        for lang, url in alternates
    )
    lastmod_line = f"    <lastmod>{html.escape(lastmod)}</lastmod>\n" if lastmod else ""
    return (
        "  <url>\n"
        f"    <loc>{html.escape(loc, quote=True)}</loc>\n"
        f"{lastmod_line}"
        f"{links}"
        f"    <priority>{priority}</priority>\n"
        "  </url>"
    )


def build_sitemap(docs: Sequence[DocEntry], config: SiteConfig) -> tuple[str, int]:
    """Build an XML sitemap with lastmod timestamps and hreflang alternates."""
    en_home = config.absolute_url("")
    zh_home = config.absolute_url("zh/")
    home_alts = (("en", en_home), ("zh-Hans", zh_home), ("x-default", en_home))
    latest_date = max((doc.lastmod for doc in docs if doc.lastmod), default=None)
    entries = [
        _sitemap_entry(en_home, "1.0", home_alts, latest_date),
        _sitemap_entry(zh_home, "0.9", home_alts, latest_date),
    ]
    for doc in docs:
        loc = config.absolute_url(doc.url_path)
        alts: list[tuple[str, str]] = []
        if doc.alternate_url is not None:
            other_loc = config.absolute_url(doc.alternate_url)
            en_loc = other_loc if doc.lang == "zh" else loc
            zh_loc = loc if doc.lang == "zh" else other_loc
            alts = [("en", en_loc), ("zh-Hans", zh_loc), ("x-default", en_loc)]
        priority = "0.9" if doc.url_path in {"docs/", "zh/docs/"} else "0.7"
        entries.append(_sitemap_entry(loc, priority, alts, doc.lastmod))

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    return xml, len(entries)


def build_robots(config: SiteConfig) -> str:
    """Build robots.txt pointing search crawlers to sitemap.xml."""
    return f"User-agent: *\nAllow: /\n\nSitemap: {config.absolute_url('sitemap.xml')}\n"


def _llms_featured_links(config: SiteConfig) -> list[str]:
    return [
        "## Featured 5-Minute Walkthrough",
        "",
        (
            "- [Detect train/test duplicate images & offline delivery verification (EN)]"
            f"({config.absolute_url('docs/dataset-delivery/')}): Download the 3-image sample, "
            "catch cross-split leakage, create a 2-image corrected version, and verify with "
            "`datakeel reconcile` offline."
        ),
        (
            "- [检查图片训练集与测试集重复泄漏并离线验包 (ZH)]"
            f"({config.absolute_url('zh/docs/dataset-delivery/')}): 下载 3 张图样例\uff0c"
            "本地定位跨划分重复图并生成 2 张图修正版本\uff0c"
            "再用 `datakeel reconcile` 离线核验\u3002"
        ),
        (
            "- [Download 3-image sample archive (ZIP)]"
            f"({config.absolute_url('assets/samples/warehouse-leakage-sample.zip')})"
        ),
        "",
    ]


def build_llms_txt(docs: Sequence[DocEntry], config: SiteConfig) -> str:
    """Build a concise llms.txt index following the llms.txt specification."""
    lines = [
        "# Datakeel",
        "",
        (
            "> Local-first, Apache-2.0 workbench for auditable AI datasets, traceable business "
            "metrics with lineage, and human-approved Agent/MCP controlled actions."
        ),
        "",
        "## Quick Start",
        "",
        "```bash",
        "uvx datakeel demo",
        "```",
        "",
        "## Core Links",
        "",
        f"- [English Home]({config.absolute_url('')})",
        f"- [Chinese Home]({config.absolute_url('zh/')})",
        "- [PyPI Package](https://pypi.org/project/datakeel/)",
        f"- [GitHub Repository]({config.repo_url})",
        f"- [Releases]({config.repo_url}/releases)",
        f"- [Extended LLM Reference]({config.absolute_url('llms-full.txt')})",
        "",
        *_llms_featured_links(config),
    ]
    by_section: dict[str, list[DocEntry]] = defaultdict(list)
    section_names: dict[str, str] = {}
    for doc in docs:
        if doc.lang == "zh" and doc.alternate_url is not None:
            continue
        by_section[doc.section_id].append(doc)
        section_names[doc.section_id] = doc.section_en

    for section_id, items in by_section.items():
        lines.extend([f"## {section_names[section_id]}", ""])
        lines.extend(
            f"- [{doc.title}]({config.absolute_url(doc.url_path)}): {doc.description}"
            for doc in items
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _llms_walkthrough_section(config: SiteConfig) -> list[str]:
    return [
        "## 5-Minute Walkthrough: Train/Test Image Leakage & Offline Verification",
        "",
        (
            "To check whether annotated images leaked across train and test folders locally "
            "and let recipients verify the delivered archive offline without a database:"
        ),
        (
            "- Download the 3-image sample archive: "
            f"{config.absolute_url('assets/samples/warehouse-leakage-sample.zip')}"
        ),
        (
            "- Import the folder (`train/loading-bay`, `test/loading-bay-copy`, "
            "`test/entrance`), run Directory split check: Datakeel blocks delivery and flags "
            "exact SHA-256 and perceptual dHash leakage (`Identical Content · Distance 0`, "
            "`Similar Images · Distance 0`) between `train/loading-bay/image.png` and "
            "`test/loading-bay-copy/image.png`."
        ),
        (
            "- Exclude the leaked test copy to create a new immutable 2-file version "
            "(`train=1, test=1`) while keeping the original 3-file version as baseline, "
            "re-check to confirm 0 leakage pairs, approve release `v1.0.0`, and export "
            "`v1.0.0.tar.gz`."
        ),
        (
            "- Recipients run `uvx datakeel reconcile v1.0.0.tar.gz` (or `--json`) offline "
            "to verify all 6 categories (file count, bytes, SHA-256 hashes, annotations, "
            "metadata, lineage) plus `delivery_review` (`directory-leakage-v1`, `leakage=0`)."
        ),
        f"- Guide (EN): {config.absolute_url('docs/dataset-delivery/')}",
        f"- Guide (ZH): {config.absolute_url('zh/docs/dataset-delivery/')}",
        "",
    ]


def build_llms_full_txt(docs: Sequence[DocEntry], config: SiteConfig) -> str:
    """Build an expanded machine-readable overview for AI search engines and agents."""
    lines = [
        "# Datakeel - Full Product & Documentation Reference",
        "",
        f"- Version: {config.version}",
        "- License: Apache-2.0",
        f"- Website: {config.normalized_base_url}",
        f"- Repository: {config.repo_url}",
        "- Stack: Python 3.12, FastAPI, SQLite / PostgreSQL, Local / S3 storage, React SPA, MCP",
        "",
        "## Three Core Workflows",
        "",
    ]
    for pillar in pillars_for("en"):
        lines.extend([f"### {pillar.eyebrow}: {pillar.title}", pillar.summary])
        lines.extend(f"- {bullet}" for bullet in pillar.bullets)
        lines.append("")

    lines.extend(["## Positioning vs. Point Tools", ""])
    lines.extend(
        f"- **{row.capability}**: {row.datakeel} (vs. {row.single_purpose})"
        for row in comparison_for("en")
    )
    lines.extend(["", "## Frequently Asked Questions", ""])
    for faq in faq_for("en"):
        lines.extend([f"### {faq.question}", faq.answer, ""])

    lines.extend(_llms_walkthrough_section(config))
    lines.extend(
        [
            "## MCP Server Integration",
            "",
            (
                "Datakeel exposes audited read and plan-preparation tools over local stdio "
                "(`uv run datakeel mcp`) or loopback SSE (`uv run datakeel mcp --transport sse`). "
                "MCP never exposes approval or write-execution tools; humans sign plans."
            ),
            "",
            "## Documentation Index",
            "",
        ]
    )
    lines.extend(
        f"- [{doc.lang.upper()}] {doc.title} - {config.absolute_url(doc.url_path)} "
        f"({doc.source_rel}): {doc.description}"
        for doc in docs
    )
    return "\n".join(lines).rstrip() + "\n"


def write_seo_files(docs: Sequence[DocEntry], config: SiteConfig) -> int:
    """Write sitemap.xml, robots.txt, llms.txt, llms-full.txt, and .nojekyll."""
    sitemap_xml, url_count = build_sitemap(docs, config)
    (config.output_dir / "sitemap.xml").write_text(sitemap_xml, encoding="utf-8")
    (config.output_dir / "robots.txt").write_text(build_robots(config), encoding="utf-8")
    (config.output_dir / "llms.txt").write_text(build_llms_txt(docs, config), encoding="utf-8")
    (config.output_dir / "llms-full.txt").write_text(
        build_llms_full_txt(docs, config), encoding="utf-8"
    )
    (config.output_dir / ".nojekyll").write_text("", encoding="utf-8")
    return url_count
