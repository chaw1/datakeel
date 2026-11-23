# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Render bilingual editorial landing pages with SoftwareApplication and FAQPage JSON-LD."""

from __future__ import annotations

import html
from collections import defaultdict
from typing import TYPE_CHECKING

from scripts.docs_site.content import landing_for
from scripts.docs_site.models import PageMeta
from scripts.docs_site.templates import render_shell

if TYPE_CHECKING:
    from collections.abc import Sequence

    from scripts.docs_site.models import DocEntry, LanguageCode, LocalizedLanding, SiteConfig


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _render_pillars(copy: LocalizedLanding, config: SiteConfig) -> str:
    cards: list[str] = []
    for item in copy.pillars:
        bullets = "".join(f"<li>{_esc(b)}</li>" for b in item.bullets)
        href = _esc(config.href(item.doc_href))
        cards.append(
            '<article class="sheet-card">'
            f'<div class="pillar-meta"><span class="pillar-index">{_esc(item.index)}</span>'
            f"<span>{_esc(item.eyebrow)}</span></div>"
            f"<h3>{_esc(item.title)}</h3><p>{_esc(item.summary)}</p>"
            f'<ul class="pillar-list">{bullets}</ul>'
            f'<a class="card-link" href="{href}">{_esc(item.doc_label)}</a>'
            "</article>"
        )
    return "".join(cards)


def _render_docs_grid(docs: Sequence[DocEntry], lang: LanguageCode, config: SiteConfig) -> str:
    by_section: dict[str, list[DocEntry]] = defaultdict(list)
    titles: dict[str, str] = {}
    preferred = {doc.url_path for doc in docs if doc.lang == lang}
    for doc in docs:
        if doc.url_path in {"docs/", "zh/docs/"}:
            continue
        if doc.lang != lang and doc.alternate_url in preferred:
            continue
        by_section[doc.section_id].append(doc)
        titles[doc.section_id] = doc.section_zh if lang == "zh" else doc.section_en

    cards: list[str] = []
    for section_id, items in by_section.items():
        links = "".join(
            f'<li><a href="{_esc(config.href(doc.url_path))}">{_esc(doc.title)}</a></li>'
            for doc in items[:6]
        )
        cards.append(
            f'<div class="sheet-card"><h3>{_esc(titles[section_id])}</h3>'
            f'<ul class="doc-group-list">{links}</ul></div>'
        )
    return "".join(cards)


def _render_hero_section(copy: LocalizedLanding, config: SiteConfig) -> str:
    qs_cmd = (
        "uvx datakeel demo\n"
        "# Web UI: http://127.0.0.1:8765  |  API Docs: http://127.0.0.1:8765/api/docs\n"
        f"# Or from source: git clone {config.repo_url}.git && cd datakeel && uv sync --locked"
    )
    docs_href = _esc(config.href(copy.docs_href))
    tour_href = _esc(config.href(copy.tour_href))
    hero_img = _esc(config.href(copy.hero_img))
    pypi_badge = (
        '<a class="badge badge-pencil" href="https://pypi.org/project/datakeel/">'
        f"PyPI v{_esc(config.version)}</a>"
    )
    return f"""<section class="hero">
    <div class="hero-eyebrow">
      <span class="badge badge-ok">Apache-2.0</span>
      {pypi_badge}
      <span class="badge">Local-First | Python 3.12+ | SQLite / PostgreSQL</span>
      <span class="badge badge-stamp">Human-Approved Writes</span>
    </div>
    <h1>{_esc(copy.h1)}</h1>
    <p class="hero-lead">{_esc(copy.lead)}</p>
    <div class="hero-actions">
      <a class="btn-primary" href="{docs_href}">{_esc(copy.cta_docs)}</a>
      <a class="btn-secondary" href="{tour_href}">{_esc(copy.cta_tour)}</a>
      <a class="btn-secondary" href="{_esc(config.repo_url)}">{_esc(copy.cta_github)}</a>
    </div>
    <div class="quickstart-card">
      <div class="quickstart-bar">
        <span>{_esc(copy.qs_bar)}</span>
        <button type="button" class="copy-btn" data-copy-target="quickstart-code"
                data-copied-label="{_esc(copy.copied_label)}">{_esc(copy.copy_label)}</button>
      </div>
      <pre><code id="quickstart-code">{_esc(qs_cmd)}</code></pre>
    </div>
    <figure class="proof-frame">
      <img src="{hero_img}" alt="{_esc(copy.hero_caption)}" width="1280" height="720" />
      <figcaption>{_esc(copy.hero_caption)}</figcaption>
    </figure>
  </section>"""


def _render_visuals_and_compare(copy: LocalizedLanding, config: SiteConfig) -> str:
    compare_rows = "".join(
        f"<tr><td><strong>{_esc(row.capability)}</strong></td>"
        f"<td>{_esc(row.datakeel)}</td><td>{_esc(row.single_purpose)}</td></tr>"
        for row in copy.comparison
    )
    evidence_img = _esc(config.href(copy.evidence_img))
    arch_img = _esc(config.href("assets/images/architecture-overview.svg"))
    return f"""<section class="section" id="visuals">
    <div class="section-head">
      <span class="section-kicker">{_esc(copy.visual_kicker)}</span>
      <h2>{_esc(copy.visual_h2)}</h2>
    </div>
    <div class="visual-grid">
      <figure class="proof-frame">
        <img src="{evidence_img}" alt="{_esc(copy.visual_cap1)}" loading="lazy" />
        <figcaption>{_esc(copy.visual_cap1)}</figcaption>
      </figure>
      <figure class="proof-frame">
        <img src="{arch_img}" alt="{_esc(copy.visual_cap2)}" loading="lazy" />
        <figcaption>{_esc(copy.visual_cap2)}</figcaption>
      </figure>
    </div>
  </section>
  <section class="section" id="compare">
    <div class="section-head">
      <span class="section-kicker">{_esc(copy.compare_kicker)}</span>
      <h2>{_esc(copy.compare_h2)}</h2>
      <p class="section-lead">{_esc(copy.compare_lead)}</p>
    </div>
    <div class="table-wrap">
      <table class="data-table">
        <thead><tr>
          <th>{_esc(copy.th_cap)}</th><th>{_esc(copy.th_dk)}</th><th>{_esc(copy.th_other)}</th>
        </tr></thead>
        <tbody>{compare_rows}</tbody>
      </table>
    </div>
  </section>"""


def _render_docs_and_faq(
    copy: LocalizedLanding,
    lang: LanguageCode,
    docs: Sequence[DocEntry],
    config: SiteConfig,
) -> str:
    faq_cards = "".join(
        f'<article class="faq-item"><h3>{_esc(item.question)}</h3>'
        f"<p>{_esc(item.answer)}</p></article>"
        for item in copy.faq
    )
    return f"""<section class="section" id="docs">
    <div class="section-head">
      <span class="section-kicker">{_esc(copy.docs_kicker)}</span>
      <h2>{_esc(copy.docs_h2)}</h2>
    </div>
    <div class="docs-grid">{_render_docs_grid(docs, lang, config)}</div>
  </section>
  <section class="section" id="faq">
    <div class="section-head">
      <span class="section-kicker">{_esc(copy.faq_kicker)}</span>
      <h2>{_esc(copy.faq_h2)}</h2>
    </div>
    <div class="faq-list">{faq_cards}</div>
  </section>"""


def _landing_json_ld(
    copy: LocalizedLanding,
    config: SiteConfig,
) -> tuple[dict[str, object], ...]:
    software_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "Datakeel",
        "applicationCategory": "DeveloperApplication",
        "operatingSystem": "Linux, macOS, Windows",
        "softwareVersion": config.version,
        "license": "https://www.apache.org/licenses/LICENSE-2.0",
        "url": config.absolute_url(copy.url_path),
        "codeRepository": config.repo_url,
        "description": copy.meta_desc,
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
    }
    faq_ld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item.question,
                "acceptedAnswer": {"@type": "Answer", "text": item.answer},
            }
            for item in copy.faq
        ],
    }
    return (software_ld, faq_ld)


def render_landing_page(
    lang: LanguageCode,
    docs: Sequence[DocEntry],
    config: SiteConfig,
) -> str:
    """Render the English or Chinese landing page with rich SEO/GEO structured data."""
    copy = landing_for(lang)
    hero_html = _render_hero_section(copy, config)
    pillars_html = (
        '<section class="section" id="pillars"><div class="section-head">'
        f'<span class="section-kicker">{_esc(copy.pillars_kicker)}</span>'
        f"<h2>{_esc(copy.pillars_h2)}</h2>"
        f'<p class="section-lead">{_esc(copy.pillars_lead)}</p></div>'
        f'<div class="pillars-grid">{_render_pillars(copy, config)}</div></section>'
    )
    visuals_html = _render_visuals_and_compare(copy, config)
    docs_faq_html = _render_docs_and_faq(copy, lang, docs, config)
    body = (
        '<main class="container">\n'
        f"  {hero_html}\n  {pillars_html}\n  {visuals_html}\n  {docs_faq_html}\n</main>"
    )
    meta = PageMeta(
        lang=lang,
        title=copy.page_title,
        description=copy.meta_desc,
        url_path=copy.url_path,
        alternate_url=copy.alt_url,
        switch_href=config.href(copy.alt_url),
        json_ld_blocks=_landing_json_ld(copy, config),
    )
    return render_shell(config, meta, body)
