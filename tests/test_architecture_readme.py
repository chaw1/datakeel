# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The README diagram is the current self-contained architecture overview."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SVG = ROOT / "docs/images/architecture-overview.svg"


def test_svg_when_parsed_has_current_overview_dimensions_and_accessible_names() -> None:
    """The sole diagram preserves the source overview and has a title and description."""
    root = ET.fromstring(SVG.read_bytes())  # noqa: S314  # Repository-owned static SVG.
    assert root.attrib["viewBox"] == "0 0 1200 850"
    assert root.attrib["role"] == "img"
    text = " ".join(root.itertext())
    for expected in (
        "Datakeel 当前架构总览",
        "Browser · React SPA",
        "FastAPI · api 进程",
        "worker 进程",
        "应用服务层",
        "领域与同层服务",
        "数据库 · SQLite / PostgreSQL",
        "对象存储 · 本地目录 / S3",
    ):
        assert expected in text
    for target_only in ("OpenTelemetry", "Ontology SDK", "DBOS", "Merkle", "roadmap"):
        assert target_only not in text


def test_svg_when_scanned_has_no_external_resources_or_executable_content() -> None:
    """The image works without HTML CSS, remote fonts, scripts, or local metadata."""
    root = ET.fromstring(SVG.read_bytes())  # noqa: S314  # Repository-owned static SVG.
    for element in root.iter():
        assert element.tag.rsplit("}", 1)[-1] not in {"script", "foreignObject"}
        for name, value in element.attrib.items():
            local = name.rsplit("}", 1)[-1].lower()
            assert local not in {"href", "src"}
            assert not local.startswith("on")
            assert "var(--" not in value
    content = SVG.read_text()
    assert "@import" not in content
    assert "url(" not in content.replace("url(#arrow-overview)", "")
    assert "currentColor" not in content
    assert "architecture.html" not in content


def test_readmes_when_replacing_mermaid_share_one_relative_current_svg() -> None:
    """Both languages link the same current image without retaining the old diagram."""
    expected = "(docs/images/architecture-overview.svg)"
    for name in ("README.md", "README.zh.md"):
        content = (ROOT / name).read_text()
        assert content.count(expected) == 1
        assert "```mermaid" not in content
        assert "datakeel:local" in content
        assert "export-traces" in content
