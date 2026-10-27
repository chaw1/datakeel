# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Escape standalone Markdown and HTML exports while retaining per-sentence evidence."""

import html
import json
import re

from datakeel.core.datasheet_models import DatasheetDocument, DatasheetFact, DatasheetLanguage
from datakeel.datasheets.vocabulary import missing_text


def _empty_text(language: DatasheetLanguage, *, missing: bool) -> str:
    if missing:
        return missing_text(language)
    if language == "en":
        return "No sentence passed citation validation."
    return "没有保留通过引用校验的句子。"


def _fact_value(fact: DatasheetFact) -> str:
    return json.dumps(fact.value, ensure_ascii=False, sort_keys=True)


def _md(value: str) -> str:
    escaped = html.escape(value, quote=False)
    escaped = re.sub(r"([\\`*\[\]{}_!|#~])", r"\\\1", escaped)
    # One exported line per value: no line breaks, and no list marker where a line starts.
    inline = " ".join(part.strip() for part in escaped.splitlines() if part.strip())
    return re.sub(r"^(?:([-+])|(\d+)([.)]))", r"\2\\\1\3", inline)


def _heading(document: DatasheetDocument) -> str:
    return "Dataset datasheet" if document.language == "en" else "数据集说明书"


def render_markdown(document: DatasheetDocument) -> str:
    """Export readable chapters, linked citations, facts and the rejection ledger."""
    lines = [
        f"# {_heading(document)}",
        "",
        f"{_md(document.dataset_id)} / {_md(document.version_id)}",
        "",
    ]
    if document.stale:
        lines.extend(["**Outdated / 已过期**", ""])
    for section in document.sections:
        lines.extend([f"## {_md(section.title)}", ""])
        if not section.sentences:
            lines.extend([_empty_text(document.language, missing=section.missing), ""])
        for sentence in section.sentences:
            citations = " ".join(f"[{_md(key)}](#fact-{_md(key)})" for key in sentence.fact_ids)
            lines.extend([f"{_md(sentence.text)} {citations}", ""])
    lines.extend(["## Facts / 依据事实", ""])
    for fact in document.facts:
        lines.extend(
            [
                f'<a id="fact-{html.escape(fact.id, quote=True)}"></a>',
                f"- **{_md(fact.id)}**: {_md(_fact_value(fact))}",
                f"  - {_md(fact.source_type)} / {_md(fact.source_id)} / {_md(fact.field)}",
                f"  - {_md(fact.recorded_at.isoformat())}",
                "",
            ]
        )
    lines.extend(["## Dropped sentences / 删除的句子", ""])
    lines.extend(
        f"- {_md(item.text)} — {_md(', '.join(item.reasons))} [{_md(', '.join(item.fact_ids))}]"
        for item in document.dropped_sentences
    )
    return "\n".join(lines) + "\n"


def _sentence_html(text: str, fact_ids: tuple[str, ...], facts: dict[str, DatasheetFact]) -> str:
    values = "\n".join(f"{key}: {_fact_value(facts[key])}" for key in fact_ids if key in facts)
    references = " ".join(
        f'<a href="#fact-{html.escape(key, quote=True)}">[{html.escape(key)}]</a>'
        for key in fact_ids
    )
    ids_attribute = html.escape(" ".join(fact_ids), quote=True)
    return (
        f'<p><span class="datasheet-sentence" data-fact-ids="{ids_attribute}" '
        f'title="{html.escape(values, quote=True)}">{html.escape(text)}</span> {references}</p>'
    )


def _fact_html(fact: DatasheetFact) -> str:
    source = f"{fact.source_type} / {fact.source_id} / {fact.field}"
    identity = html.escape(fact.id, quote=True)
    return (
        f'<li id="fact-{identity}"><strong>{html.escape(fact.id)}</strong>: '
        f"{html.escape(_fact_value(fact))}<br><small>{html.escape(source)} · "
        f"{html.escape(fact.recorded_at.isoformat())}</small></li>"
    )


def render_html(document: DatasheetDocument) -> str:
    """Build a script-free standalone HTML page with accessible citation links and tooltips."""
    title = _heading(document)
    facts = {fact.id: fact for fact in document.facts}
    parts = [
        "<!doctype html>",
        f'<html lang="{document.language}"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        (
            '<meta http-equiv="Content-Security-Policy" '
            "content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        ),
        f"<title>{html.escape(title)}</title>",
        (
            "<style>body{font:16px/1.6 system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}"
            ".datasheet-sentence{border-bottom:1px dotted}small{font-size:.875rem}"
            "li{overflow-wrap:anywhere}a{color:#1748a6}</style></head><body>"
        ),
        f"<h1>{html.escape(title)}</h1>",
        f"<p>{html.escape(document.dataset_id)} / {html.escape(document.version_id)}</p>",
    ]
    if document.stale:
        parts.append("<p><strong>Outdated / 已过期</strong></p>")
    for section in document.sections:
        parts.append(f"<section><h2>{html.escape(section.title)}</h2>")
        if not section.sentences:
            parts.append(f"<p>{_empty_text(document.language, missing=section.missing)}</p>")
        parts.extend(_sentence_html(item.text, item.fact_ids, facts) for item in section.sentences)
        parts.append("</section>")
    parts.append("<h2>Facts / 依据事实</h2><ul>")
    parts.extend(_fact_html(fact) for fact in document.facts)
    parts.append("</ul><h2>Dropped sentences / 删除的句子</h2><ul>")
    parts.extend(
        f"<li>{html.escape(item.text)} — {html.escape(', '.join(item.reasons))}</li>"
        for item in document.dropped_sentences
    )
    parts.append("</ul></body></html>")
    return "\n".join(parts)
