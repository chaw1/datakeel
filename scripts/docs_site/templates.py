# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTML layout templates, SEO metadata, JSON-LD, and documentation page renderer."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from typing import TYPE_CHECKING

from scripts.docs_site.models import PageMeta

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.docs_site.models import DocEntry, LanguageCode, RenderedDoc, SiteConfig


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _json_ld_script(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    return f'<script type="application/ld+json">{serialized}</script>'


def _alternate_links(config: SiteConfig, meta: PageMeta, canonical: str) -> str:
    self_lang = "zh-Hans" if meta.lang == "zh" else "en"
    links = [f'<link rel="alternate" hreflang="{self_lang}" href="{_esc(canonical)}" />']
    if meta.alternate_url is not None:
        other_lang = "en" if meta.lang == "zh" else "zh-Hans"
        other_abs = config.absolute_url(meta.alternate_url)
        default_url = other_abs if meta.lang == "zh" else canonical
        links.append(f'<link rel="alternate" hreflang="{other_lang}" href="{_esc(other_abs)}" />')
        links.append(f'<link rel="alternate" hreflang="x-default" href="{_esc(default_url)}" />')
    return "\n  ".join(links)


def _head_html(config: SiteConfig, meta: PageMeta) -> str:
    canonical = config.absolute_url(meta.url_path)
    og_image = config.absolute_url(f"assets/og-{meta.lang}.png")
    html_lang = "zh-CN" if meta.lang == "zh" else "en"
    og_locale = "zh_CN" if meta.lang == "zh" else "en_US"
    alternates = _alternate_links(config, meta, canonical)
    ld_html = "\n  ".join(_json_ld_script(item) for item in meta.json_ld_blocks)
    favicon_href = _esc(config.href("assets/favicon.svg"))
    css_href = _esc(config.href("assets/site.css"))
    return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(meta.title)}</title>
  <meta name="description" content="{_esc(meta.description)}" />
  <meta name="theme-color" content="#F7F5EE" media="(prefers-color-scheme: light)" />
  <meta name="theme-color" content="#171716" media="(prefers-color-scheme: dark)" />
  <link rel="canonical" href="{_esc(canonical)}" />
  {alternates}
  <link rel="icon" type="image/svg+xml" href="{favicon_href}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Datakeel" />
  <meta property="og:locale" content="{og_locale}" />
  <meta property="og:title" content="{_esc(meta.title)}" />
  <meta property="og:description" content="{_esc(meta.description)}" />
  <meta property="og:url" content="{_esc(canonical)}" />
  <meta property="og:image" content="{_esc(og_image)}" />
  <meta property="og:image:width" content="1200" />
  <meta property="og:image:height" content="630" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{_esc(meta.title)}" />
  <meta name="twitter:description" content="{_esc(meta.description)}" />
  <meta name="twitter:image" content="{_esc(og_image)}" />
  <link rel="stylesheet" href="{css_href}" />
  {ld_html}
</head>"""


def _header_html(config: SiteConfig, meta: PageMeta) -> str:
    is_zh = meta.lang == "zh"
    home_href = config.href("zh/" if is_zh else "")
    docs_href = config.href("zh/docs/" if is_zh else "docs/")
    nav_links = (
        (docs_href, "文档中心" if is_zh else "Docs", meta.is_docs),
        (f"{home_href}#pillars", "核心能力" if is_zh else "Capabilities", False),
        (f"{home_href}#compare", "定位对比" if is_zh else "Compare", False),
        (f"{home_href}#faq", "常见问题" if is_zh else "FAQ", False),
        (config.repo_url, "GitHub", False),
    )
    nav_items = "".join(
        f'<a href="{_esc(href)}"'
        + (' aria-current="page"' if active else "")
        + f">{_esc(label)}</a>"
        for href, label, active in nav_links
    )
    menu_label = "目录" if is_zh else "Menu"
    menu_btn = (
        f'<button type="button" class="pill-btn menu-toggle" data-sidebar-toggle '
        f'aria-expanded="false">{menu_label}</button>'
        if meta.is_docs
        else ""
    )
    logo_src = _esc(config.href("assets/favicon.svg"))
    switch_label = "English" if is_zh else "中文"
    theme_label = "明暗" if is_zh else "Theme"
    return f"""<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="{_esc(home_href)}">
      <img src="{logo_src}" alt="Datakeel logo" width="28" height="28" />
      <span>Datakeel</span>
    </a>
    <nav class="header-nav" aria-label="Primary">{nav_items}</nav>
    <div class="header-actions">
      {menu_btn}
      <a class="pill-btn" href="{_esc(meta.switch_href)}">{switch_label}</a>
      <button type="button" class="pill-btn" data-theme-toggle>{theme_label}</button>
    </div>
  </div>
</header>"""


def _footer_html(config: SiteConfig, lang: LanguageCode) -> str:
    docs_href = config.href("zh/docs/" if lang == "zh" else "docs/")
    note = (
        f"Datakeel v{config.version} - Apache-2.0 开源许可 - 本地优先可审计数据工作台"
        if lang == "zh"
        else f"Datakeel v{config.version} - Apache-2.0 - Local-first auditable data workbench"
    )
    links = (
        (config.repo_url, "GitHub"),
        (f"{config.repo_url}/releases", "Releases"),
        (docs_href, "文档" if lang == "zh" else "Docs"),
        (config.href("llms.txt"), "llms.txt"),
        (config.href("sitemap.xml"), "sitemap.xml"),
    )
    rendered_links = "".join(f'<a href="{_esc(href)}">{_esc(label)}</a>' for href, label in links)
    js_src = _esc(config.href("assets/site.js"))
    return f"""<footer class="site-footer">
  <div class="footer-inner">
    <span>{_esc(note)}</span>
    <div class="footer-links">{rendered_links}</div>
  </div>
</footer>
<script defer src="{js_src}"></script>
</body>
</html>"""


def render_shell(config: SiteConfig, meta: PageMeta, body_html: str) -> str:
    """Wrap body markup in the full SEO-ready HTML document shell."""
    head = _head_html(config, meta)
    header = _header_html(config, meta)
    footer = _footer_html(config, meta.lang)
    return f"{head}\n<body>\n{header}\n{body_html}\n{footer}\n"


def _render_sidebar(
    all_docs: Sequence[DocEntry],
    active_url: str,
    lang: LanguageCode,
    config: SiteConfig,
) -> str:
    by_section: dict[str, list[DocEntry]] = defaultdict(list)
    section_titles: dict[str, str] = {}
    chosen_urls = {doc.url_path for doc in all_docs if doc.lang == lang}
    for doc in all_docs:
        if doc.lang != lang and doc.alternate_url in chosen_urls:
            continue
        by_section[doc.section_id].append(doc)
        section_titles[doc.section_id] = doc.section_zh if lang == "zh" else doc.section_en

    groups: list[str] = []
    for section_id, items in by_section.items():
        links = "".join(
            f'<li><a href="{_esc(config.href(item.url_path))}"'
            + (' aria-current="page"' if item.url_path == active_url else "")
            + f">{_esc(item.title)}</a></li>"
            for item in items
        )
        title = _esc(section_titles[section_id])
        groups.append(
            f'<div class="sidebar-group"><h2 class="sidebar-title">{title}</h2>'
            f'<ul class="sidebar-links">{links}</ul></div>'
        )
    return "".join(groups)


def _doc_json_ld(entry: DocEntry, config: SiteConfig) -> tuple[dict[str, object], ...]:
    is_zh = entry.lang == "zh"
    home_label = "首页" if is_zh else "Home"
    docs_label = "文档" if is_zh else "Docs"
    home_url = config.absolute_url("zh/" if is_zh else "")
    docs_url = config.absolute_url("zh/docs/" if is_zh else "docs/")
    article_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        "headline": entry.title,
        "description": entry.description,
        "inLanguage": "zh-CN" if is_zh else "en",
        "url": config.absolute_url(entry.url_path),
        "author": {"@type": "Organization", "name": "Datakeel Contributors"},
        "isPartOf": {"@type": "WebSite", "name": "Datakeel", "url": config.normalized_base_url},
    }
    if entry.lastmod:
        article_ld["dateModified"] = entry.lastmod
    breadcrumb_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": home_label, "item": home_url},
            {"@type": "ListItem", "position": 2, "name": docs_label, "item": docs_url},
            {
                "@type": "ListItem",
                "position": 3,
                "name": entry.title,
                "item": config.absolute_url(entry.url_path),
            },
        ],
    }
    return (article_ld, breadcrumb_ld)


def render_doc_page(
    rendered: RenderedDoc,
    all_docs: Sequence[DocEntry],
    config: SiteConfig,
) -> str:
    """Render one documentation page with sidebar, breadcrumbs, TOC, and TechArticle JSON-LD."""
    entry = rendered.entry
    is_zh = entry.lang == "zh"
    home_href = config.href("zh/" if is_zh else "")
    docs_href = config.href("zh/docs/" if is_zh else "docs/")
    switch_href = (
        config.href(entry.alternate_url)
        if entry.alternate_url
        else config.href("docs/" if is_zh else "zh/docs/")
    )
    sidebar_html = _render_sidebar(all_docs, entry.url_path, entry.lang, config)
    toc_items = "".join(
        f'<li class="toc-h{h.level}"><a href="#{_esc(h.slug)}">{_esc(h.text)}</a></li>'
        for h in rendered.headings[:28]
    )
    toc_heading = "本页目录" if is_zh else "On this page"
    toc_html = (
        f'<aside class="doc-toc" aria-label="{toc_heading}">'
        f"<h2>{toc_heading}</h2><ul>{toc_items}</ul></aside>"
        if toc_items
        else ""
    )
    source_url = f"{config.repo_url}/blob/main/{entry.source_rel}"
    edit_label = "在 GitHub 查看源文件" if is_zh else "View source on GitHub"
    section_label = entry.section_zh if is_zh else entry.section_en
    body = f"""<div class="docs-layout">
  <aside class="docs-sidebar" data-docs-sidebar aria-label="Documentation">
    {sidebar_html}
  </aside>
  <main class="doc-article">
    <nav class="breadcrumbs" aria-label="Breadcrumb">
      <a href="{_esc(home_href)}">{"首页" if is_zh else "Home"}</a><span>/</span>
      <a href="{_esc(docs_href)}">{"文档" if is_zh else "Docs"}</a><span>/</span>
      <span>{_esc(section_label)}</span>
    </nav>
    <div class="doc-meta-row">
      <span>{_esc(entry.source_rel)}</span>
      <a href="{_esc(source_url)}">{edit_label}</a>
    </div>
    <article class="prose">{rendered.body_html}</article>
  </main>
  {toc_html}
</div>"""
    meta = PageMeta(
        lang=entry.lang,
        title=f"{entry.title} - Datakeel",
        description=entry.description,
        url_path=entry.url_path,
        alternate_url=entry.alternate_url,
        switch_href=switch_href,
        json_ld_blocks=_doc_json_ld(entry, config),
        is_docs=True,
    )
    return render_shell(config, meta, body)


def render_not_found_page(config: SiteConfig) -> str:
    """Render a clean bilingual 404 page."""
    home_en = _esc(config.href(""))
    home_zh = _esc(config.href("zh/"))
    docs_en = _esc(config.href("docs/"))
    body = f"""<main class="container">
  <section class="hero">
    <div class="hero-eyebrow">
      <span class="badge badge-stamp">404</span>
      <span>Page not found / 页面不存在</span>
    </div>
    <h1>This document could not be found.</h1>
    <p class="hero-lead">
      Browse the English or Chinese documentation hub, or return to the Datakeel landing page.
    </p>
    <div class="hero-actions">
      <a class="btn-primary" href="{home_en}">English Home</a>
      <a class="btn-secondary" href="{home_zh}">简体中文首页</a>
      <a class="btn-secondary" href="{docs_en}">Documentation Hub</a>
    </div>
  </section>
</main>"""
    meta = PageMeta(
        lang="en",
        title="404 - Datakeel",
        description="Page not found in Datakeel documentation.",
        url_path="404.html",
        switch_href=config.href("zh/"),
    )
    return render_shell(config, meta, body)
