# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build the complete static documentation and landing site."""

from __future__ import annotations

import shutil
import tomllib
from typing import TYPE_CHECKING

from scripts.docs_site.assets import copy_site_assets
from scripts.docs_site.catalog import discover_docs
from scripts.docs_site.landing import render_landing_page
from scripts.docs_site.markdown_render import render_document
from scripts.docs_site.models import BuildSummary, SiteConfig
from scripts.docs_site.seo import write_seo_files
from scripts.docs_site.templates import render_doc_page, render_not_found_page

if TYPE_CHECKING:
    from pathlib import Path


def read_package_version(repo_root: Path) -> str:
    """Read the project version string from pyproject.toml."""
    manifest = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(manifest["project"]["version"])


def _write_page(output_dir: Path, rel_url: str, html_text: str) -> None:
    cleaned = rel_url.strip("/")
    target = output_dir / cleaned / "index.html" if cleaned else output_dir / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html_text, encoding="utf-8")


def build_site(config: SiteConfig) -> BuildSummary:
    """Generate the bilingual landing pages, rendered documentation, assets, and SEO files."""
    if config.output_dir.exists():
        shutil.rmtree(config.output_dir)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    docs = discover_docs(config.repo_root)
    doc_url_map = {doc.source_rel: doc.url_path for doc in docs}
    assets_copied = copy_site_assets(config)

    _write_page(config.output_dir, "", render_landing_page("en", docs, config))
    _write_page(config.output_dir, "zh/", render_landing_page("zh", docs, config))
    (config.output_dir / "404.html").write_text(render_not_found_page(config), encoding="utf-8")

    for entry in docs:
        rendered = render_document(entry, config.repo_root, doc_url_map, config)
        html_doc = render_doc_page(rendered, docs, config)
        _write_page(config.output_dir, entry.url_path, html_doc)

    sitemap_urls = write_seo_files(docs, config)
    return BuildSummary(
        pages_written=len(docs) + 3,
        docs_written=len(docs),
        assets_copied=assets_copied,
        sitemap_urls=sitemap_urls,
    )
