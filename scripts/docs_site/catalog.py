# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Discover bilingual documentation pages, sections, and metadata from the repository."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from scripts.docs_site.models import DocEntry, LanguageCode

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_MARKUP_RE = re.compile(r"[`*~<>]")
_EMPHASIS_UNDERSCORE_RE = re.compile(r"(?<!\w)_+|_+(?!\w)")
_WHITESPACE_RE = re.compile(r"\s+")

_MIN_DESC_CHARS = 28
_MAX_DESC_CHARS = 165
_TRUNCATED_DESC_CHARS = 162
_MAX_NAV_DOTS = 2
_TRAILING_PUNCT = " ,.;:\uff0c\u3002\uff1b\uff1a"

_DESCRIPTION_OVERRIDES: dict[str, str] = {
    "docs/README.md": (
        "Complete Datakeel documentation index covering dataset delivery, visual QA, "
        "Ask data metrics, lineage, controlled MCP actions, deployment, and API reference."
    ),
    "docs/README.zh.md": (
        "Datakeel 完整中文文档目录\uff1a覆盖数据集交付审查\u3001视觉校样\u3001可追溯问数\u3001"
        "数据血缘\u3001受控 MCP 动作\u3001部署与接口参考\u3002"
    ),
}

_SECTIONS: dict[str, tuple[str, str, int]] = {
    "start": ("Start here", "从这里开始", 10),
    "datasets": ("Annotation, training & delivery", "标注生产\u3001训练集与交付", 20),
    "catalog": ("Catalog, Ask data & governance", "企业目录\u3001问数与治理", 30),
    "agents": ("Controlled actions, Agent & MCP", "受控动作\u3001智能体与 MCP", 40),
    "evidence": ("Evidence, media & knowledge graphs", "多模态证据\u3001媒体与知识图谱", 50),
    "operations": ("API, architecture & operations", "API\u3001架构与运维", 60),
    "engineering": ("Engineering & community", "工程规范与社区", 70),
}

_STEM_SECTION: dict[str, str] = {
    "readme": "start",
    "demo": "start",
    "dataset-delivery": "datasets",
    "production": "datasets",
    "annotation-workbench": "datasets",
    "annotation-qa": "datasets",
    "training": "datasets",
    "llm-data": "datasets",
    "datasheets": "datasets",
    "releases": "datasets",
    "ask": "catalog",
    "metadata-imports": "catalog",
    "standards": "catalog",
    "quality-rules": "catalog",
    "data-assets": "catalog",
    "timeseries": "catalog",
    "actions": "agents",
    "workflows": "agents",
    "agent": "agents",
    "one-sentence": "agents",
    "identity-access": "agents",
    "action-declarations": "agents",
    "media-quality": "evidence",
    "media": "evidence",
    "kg": "evidence",
    "vector-fake": "evidence",
    "vector-offline-evaluation": "evidence",
    "custom-operators": "evidence",
    "rust-accel": "evidence",
    "api-reference": "operations",
    "architecture": "operations",
    "persistence-schema": "operations",
    "deployment": "operations",
    "database-maintenance": "operations",
    "capacity": "operations",
    "code-standards": "engineering",
    "verification": "engineering",
    "test-speed": "engineering",
    "public-export": "engineering",
    "ui-direction-b": "engineering",
    "backlog": "engineering",
    "contracts": "engineering",
    "contributing": "engineering",
    "support": "engineering",
    "security": "engineering",
    "changelog": "engineering",
}

_EXTRA_DOCS: tuple[str, ...] = (
    "contracts/README.md",
    "CONTRIBUTING.md",
    "SUPPORT.md",
    "SECURITY.md",
    "CHANGELOG.md",
)


def _slugify_stem(stem: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def _strip_markdown(text: str) -> str:
    cleaned = _LINK_RE.sub(r"\1", text)
    cleaned = _INLINE_MARKUP_RE.sub("", cleaned)
    cleaned = _EMPHASIS_UNDERSCORE_RE.sub("", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _extract_title(text: str, fallback: str) -> str:
    match = _HEADING_RE.search(text)
    if match:
        return _strip_markdown(match.group(1))
    return fallback


def _extract_description(source_rel: str, text: str, title: str) -> str:
    if source_rel in _DESCRIPTION_OVERRIDES:
        return _DESCRIPTION_OVERRIDES[source_rel]
    without_fences = _CODE_FENCE_RE.sub("", text)
    for raw_block in without_fences.split("\n\n"):
        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if not lines or lines[0].startswith(("#", "|", "!", "<", "---", "***")):
            continue
        candidate = _strip_markdown(" ".join(line.lstrip("> ") for line in lines))
        if len(candidate) < _MIN_DESC_CHARS or candidate.count("\u00b7") >= _MAX_NAV_DOTS:
            continue
        if len(candidate) > _MAX_DESC_CHARS:
            return candidate[:_TRUNCATED_DESC_CHARS].rstrip(_TRAILING_PUNCT) + "..."
        return candidate
    return f"{title} - Datakeel documentation."


def _detect_language(source_rel: str, title: str, all_paths: set[str]) -> LanguageCode:
    if source_rel.endswith(".zh.md"):
        return "zh"
    if source_rel.endswith(".en.md"):
        return "en"
    if (source_rel[:-3] + ".en.md") in all_paths or _CJK_RE.search(title):
        return "zh"
    return "en"


def _canonical_stem(source_rel: str) -> str:
    if source_rel == "contracts/README.md":
        return "contracts"
    name = Path(source_rel).name
    for suffix in (".zh.md", ".en.md", ".md"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return _slugify_stem(name)


def _url_path_for(source_rel: str, stem: str, lang: LanguageCode, all_paths: set[str]) -> str:
    if source_rel == "docs/README.md":
        return "docs/"
    if source_rel == "docs/README.zh.md":
        return "zh/docs/"
    if source_rel.endswith(".zh.md") or (
        lang == "zh" and (source_rel[:-3] + ".en.md") in all_paths
    ):
        return f"zh/docs/{stem}/"
    return f"docs/{stem}/"


def _find_alternate(source_rel: str, all_paths: set[str]) -> str | None:
    if source_rel.endswith((".zh.md", ".en.md")):
        candidate = source_rel[:-6] + ".md"
        return candidate if candidate in all_paths else None
    for suffix in (".zh.md", ".en.md"):
        candidate = source_rel[:-3] + suffix
        if candidate in all_paths:
            return candidate
    return None


def _git_last_modified(repo_root: Path, rel_paths: list[str]) -> dict[str, str]:
    """Read latest YYYY-MM-DD commit dates for repository documents in one git call."""
    git_bin = shutil.which("git")
    if not rel_paths or git_bin is None:
        return {}
    try:
        completed = subprocess.run(  # noqa: S603  # Resolved git binary and repo-relative paths.
            [
                git_bin,
                "-C",
                str(repo_root),
                "log",
                "--format=DATE:%cs",
                "--name-only",
                "--",
                *rel_paths,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    dates: dict[str, str] = {}
    current_date = ""
    for line in completed.stdout.splitlines():
        if line.startswith("DATE:"):
            current_date = line.removeprefix("DATE:").strip()
        elif line and current_date and line not in dates:
            dates[line] = current_date
    return dates


def discover_docs(repo_root: Path) -> tuple[DocEntry, ...]:
    """Scan public Markdown documents and pair bilingual English/Chinese entries."""
    docs_dir = repo_root / "docs"
    rel_paths = sorted(path.relative_to(repo_root).as_posix() for path in docs_dir.rglob("*.md"))
    rel_paths.extend(extra for extra in _EXTRA_DOCS if (repo_root / extra).is_file())
    all_paths = set(rel_paths)
    lastmods = _git_last_modified(repo_root, rel_paths)

    preliminary: dict[str, tuple[str, str, str, LanguageCode, str]] = {}
    url_by_source: dict[str, str] = {}
    for source_rel in rel_paths:
        text = (repo_root / source_rel).read_text(encoding="utf-8")
        stem = _canonical_stem(source_rel)
        title = _extract_title(text, stem.replace("-", " ").title())
        description = _extract_description(source_rel, text, title)
        lang = _detect_language(source_rel, title, all_paths)
        url_path = _url_path_for(source_rel, stem, lang, all_paths)
        preliminary[source_rel] = (stem, title, description, lang, url_path)
        url_by_source[source_rel] = url_path

    entries: list[DocEntry] = []
    for index, source_rel in enumerate(rel_paths):
        stem, title, description, lang, url_path = preliminary[source_rel]
        section_id = _STEM_SECTION.get(stem, "engineering")
        section_en, section_zh, section_order = _SECTIONS[section_id]
        alt_source = _find_alternate(source_rel, all_paths)
        entries.append(
            DocEntry(
                source_rel=source_rel,
                url_path=url_path,
                title=title,
                description=description,
                lang=lang,
                section_id=section_id,
                section_en=section_en,
                section_zh=section_zh,
                alternate_url=url_by_source.get(alt_source) if alt_source else None,
                order=section_order * 100 + index,
                lastmod=lastmods.get(source_rel),
            )
        )
    entries.sort(key=lambda item: (item.order, item.url_path))
    return tuple(entries)
