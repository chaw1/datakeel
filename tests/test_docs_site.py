# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify the static GitHub Pages documentation site, SEO files, and workflow."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import yaml
from PIL import Image

from scripts.docs_site import SiteConfig, build_site
from scripts.docs_site.build import read_package_version
from scripts.docs_site.samples import (
    SAMPLE_ARCHIVE_REL,
    SAMPLE_ROOT_NAME,
    build_warehouse_sample_zip_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
_JSON_LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


def _extract_json_ld(html_text: str) -> list[dict[str, object]]:
    return [json.loads(block) for block in _JSON_LD_RE.findall(html_text)]


def test_build_site_generates_bilingual_pages_seo_and_social_cards(tmp_path: Path) -> None:
    """Building the static site writes bilingual landing pages, docs, SEO files, and PNG cards."""
    config = SiteConfig(
        repo_root=ROOT,
        output_dir=tmp_path / "site",
        base_url="https://datakeel.jiawis.com/",
        version=read_package_version(ROOT),
    )
    summary = build_site(config)
    out = config.output_dir

    assert summary.docs_written >= 40
    assert summary.pages_written == summary.docs_written + 3
    assert summary.sitemap_urls == summary.docs_written + 2

    for expected in (
        "index.html",
        "zh/index.html",
        "404.html",
        "docs/index.html",
        "zh/docs/index.html",
        "docs/dataset-delivery/index.html",
        "zh/docs/dataset-delivery/index.html",
        "sitemap.xml",
        "robots.txt",
        "llms.txt",
        "llms-full.txt",
        ".nojekyll",
        "assets/site.css",
        "assets/site.js",
        "assets/favicon.svg",
        "assets/og-en.png",
        "assets/og-zh.png",
        "assets/samples/warehouse-leakage-sample.zip",
    ):
        assert (out / expected).is_file(), f"Missing generated artifact: {expected}"

    for card_name in ("assets/og-en.png", "assets/og-zh.png"):
        with Image.open(out / card_name) as image:
            assert image.size == (1200, 630)

    en_home = (out / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://datakeel.jiawis.com/" />' in en_home
    assert 'hreflang="zh-Hans" href="https://datakeel.jiawis.com/zh/"' in en_home
    og_tag = 'property="og:image" content="https://datakeel.jiawis.com/assets/og-en.png"'
    assert og_tag in en_home
    ld_types = {item["@type"] for item in _extract_json_ld(en_home)}
    assert {"SoftwareApplication", "FAQPage"} <= ld_types

    zh_home = (out / "zh/index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://datakeel.jiawis.com/zh/"' in zh_home
    assert 'hreflang="en" href="https://datakeel.jiawis.com/"' in zh_home


def test_build_site_rewrites_doc_links_and_validates_sitemap(tmp_path: Path) -> None:
    """Documentation links resolve to generated pages and every sitemap URL exists on disk."""
    base_url = "https://datakeel.example/"
    config = SiteConfig(
        repo_root=ROOT,
        output_dir=tmp_path / "site",
        base_url=base_url,
        version=read_package_version(ROOT),
    )
    build_site(config)
    out = config.output_dir

    docs_hub = (out / "docs/index.html").read_text(encoding="utf-8")
    assert 'href="/docs/dataset-delivery/"' in docs_hub
    assert 'href="/zh/docs/"' in docs_hub
    assert 'href="DATASET_DELIVERY.md"' not in docs_hub
    ld_types = {item["@type"] for item in _extract_json_ld(docs_hub)}
    assert {"TechArticle", "BreadcrumbList"} <= ld_types

    llms_txt = (out / "llms.txt").read_text(encoding="utf-8")
    assert "DATAKEEL_HOME" in llms_txt
    assert "Datakeel documentation - Datakeel documentation" not in llms_txt

    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert f"Sitemap: {base_url}sitemap.xml" in robots

    sitemap_root = ET.fromstring((out / "sitemap.xml").read_bytes())  # noqa: S314  # Local output.
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text for el in sitemap_root.findall("sm:url/sm:loc", ns) if el.text]
    assert len(locs) >= 40
    for loc in locs:
        assert loc.startswith(base_url)
        rel = loc.removeprefix(base_url).strip("/")
        expected_file = out / rel / "index.html" if rel else out / "index.html"
        assert expected_file.is_file(), f"Sitemap URL missing built HTML: {loc}"


def test_pages_workflow_is_valid_and_invokes_docs_site_builder() -> None:
    """GitHub Pages workflow parses cleanly and uses the repo docs_site builder."""
    workflow_path = ROOT / ".github/workflows/pages.yml"
    content = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    assert True in parsed or "on" in parsed
    assert "scripts.docs_site" in content
    assert "actions/deploy-pages" in content
    assert "fetch-depth: 0" in content
    assert "datakeel.jiawis.com" in content


def test_warehouse_sample_archive_is_deterministic_and_has_intentional_leakage() -> None:
    """Tracked 3-image sample archive matches generator output with one cross-split duplicate."""
    archive_path = ROOT / SAMPLE_ARCHIVE_REL
    assert archive_path.is_file()
    raw_bytes = archive_path.read_bytes()
    assert raw_bytes == build_warehouse_sample_zip_bytes()

    with zipfile.ZipFile(archive_path, "r") as archive:
        names = sorted(archive.namelist())
        expected = sorted(
            f"{SAMPLE_ROOT_NAME}/{rel}"
            for rel in (
                "train/loading-bay/image.png",
                "train/loading-bay/caption.txt",
                "train/loading-bay/annotations.json",
                "test/loading-bay-copy/image.png",
                "test/loading-bay-copy/caption.txt",
                "test/loading-bay-copy/annotations.json",
                "test/entrance/image.png",
                "test/entrance/annotations.json",
            )
        )
        assert names == expected
        train_img = archive.read(f"{SAMPLE_ROOT_NAME}/train/loading-bay/image.png")
        copy_img = archive.read(f"{SAMPLE_ROOT_NAME}/test/loading-bay-copy/image.png")
        entrance_img = archive.read(f"{SAMPLE_ROOT_NAME}/test/entrance/image.png")
        assert train_img == copy_img
        assert train_img != entrance_img


def test_build_site_publishes_sample_archive_lastmod_and_case_study_links(tmp_path: Path) -> None:
    """Delivery case study links rewrite to assets/samples and sitemap includes lastmod dates."""
    base_url = "https://docs.example/datakeel/"
    config = SiteConfig(
        repo_root=ROOT,
        output_dir=tmp_path / "site",
        base_url=base_url,
        version=read_package_version(ROOT),
    )
    build_site(config)
    out = config.output_dir

    en_delivery = (out / "docs/dataset-delivery/index.html").read_text(encoding="utf-8")
    zh_delivery = (out / "zh/docs/dataset-delivery/index.html").read_text(encoding="utf-8")
    for page, img_suffix in ((en_delivery, "en"), (zh_delivery, "zh")):
        assert 'href="/datakeel/assets/samples/warehouse-leakage-sample.zip"' in page
        assert f'src="/datakeel/assets/images/dataset-import-{img_suffix}.png"' in page
        assert f'src="/datakeel/assets/images/dataset-delivery-{img_suffix}.png"' in page
        assert "directory-leakage-v1" in page

    article_ld = next(
        item for item in _extract_json_ld(en_delivery) if item.get("@type") == "TechArticle"
    )
    assert article_ld["author"] == {"@type": "Organization", "name": "Datakeel Contributors"}
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(article_ld.get("dateModified", "")))

    sitemap_root = ET.fromstring((out / "sitemap.xml").read_bytes())  # noqa: S314  # Local output.
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    lastmods = [el.text for el in sitemap_root.findall("sm:url/sm:lastmod", ns) if el.text]
    assert len(lastmods) >= 40
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in lastmods)

    llms_txt = (out / "llms.txt").read_text(encoding="utf-8")
    llms_full = (out / "llms-full.txt").read_text(encoding="utf-8")
    sample_url = f"{base_url}assets/samples/warehouse-leakage-sample.zip"
    assert sample_url in llms_txt
    assert f"{base_url}zh/docs/dataset-delivery/" in llms_txt
    assert sample_url in llms_full
    assert "directory-leakage-v1" in llms_full


def test_mcp_server_manifest_matches_readme_verification_marker() -> None:
    """Official MCP Registry server.json aligns with pyproject version and README marker."""
    manifest = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = read_package_version(ROOT)
    assert manifest["name"] == "io.github.chaw1/datakeel"
    assert len(manifest["description"]) <= 100
    assert manifest["version"] == version
    assert manifest["packages"][0]["identifier"] == "datakeel"
    assert manifest["packages"][0]["version"] == version
    assert manifest["packages"][0]["transport"]["type"] == "stdio"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"mcp-name: {manifest['name']}" in readme


def test_pypi_mcp_workflow_is_manual_dispatch_only_and_uses_oidc() -> None:
    """External PyPI/MCP publication stays strictly manual and uses OIDC without static tokens."""
    workflow_path = ROOT / ".github/workflows/publish-pypi-mcp.yml"
    content = workflow_path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(content)
    triggers = parsed.get(True) or parsed.get("on")
    assert list(triggers.keys()) == ["workflow_dispatch"]
    assert "pypa/gh-action-pypi-publish" in content
    assert "mcp-publisher login github-oidc" in content
    assert (ROOT / "docs/images/demo-walkthrough.gif").is_file()
