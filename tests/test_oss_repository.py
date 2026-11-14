# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify open-source repository documentation, metadata, compose, and release boundaries."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

_DOC_FILES = (
    "README.md",
    "README.zh.md",
    "SUPPORT.md",
    "docs/README.md",
    "docs/README.zh.md",
    "docs/API_REFERENCE.md",
    "docs/API_REFERENCE.zh.md",
    "docs/VERIFICATION.md",
    "docs/VERIFICATION.zh.md",
)
_CODE_FENCE = re.compile(r"```.*?```", flags=re.DOTALL)
_MD_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def _relative_targets(path: Path) -> list[str]:
    text = _CODE_FENCE.sub("", path.read_text(encoding="utf-8"))
    targets: list[str] = []
    for raw in _MD_LINK.findall(text):
        target = raw.strip().split()[0].strip("<>")
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        targets.append(target.split("#", 1)[0])
    return targets


def test_readme_and_docs_hub_relative_links_resolve() -> None:
    """Every relative Markdown link in READMEs and documentation hubs points to a real path."""
    missing: list[str] = []
    for relative in _DOC_FILES:
        doc = ROOT / relative
        assert doc.is_file(), f"Missing expected doc: {relative}"
        for target in _relative_targets(doc):
            if not target:
                continue
            resolved = (doc.parent / target).resolve()
            if not resolved.exists():
                missing.append(f"{relative} -> {target}")
    assert not missing, f"Broken relative links: {missing}"


def test_pyproject_exposes_pep639_compatible_package_metadata() -> None:
    """Package metadata includes URLs, keywords, authors, and valid PEP 639 classifiers."""
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = manifest["project"]
    assert project["license"] == "Apache-2.0"
    assert project["authors"]
    assert project["keywords"]
    classifiers = project["classifiers"]
    assert classifiers
    assert all(not item.startswith("License ::") for item in classifiers)
    urls = project["urls"]
    for key in ("Homepage", "Documentation", "Repository", "Issues", "Changelog"):
        assert urls.get(key), f"Missing [project.urls].{key}"


def test_community_compose_and_release_files_preserve_boundaries() -> None:
    """Community docs, loopback Compose stack, and GitHub-only release workflow stay compliant."""
    assert (ROOT / "SUPPORT.md").is_file()
    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert citation["cff-version"] == "1.2.0"
    assert citation["license"] == "Apache-2.0"
    assert citation["authors"]

    issue_config = yaml.safe_load(
        (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
    )
    assert issue_config["contact_links"]

    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    assert "ports" not in services["postgres"]
    assert services["api"]["ports"] == ["127.0.0.1:8765:8765"]
    for name in ("migrate", "api", "worker"):
        assert services[name]["image"] == "datakeel:local"

    release_text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    release = yaml.safe_load(release_text)
    assert True in release or "on" in release
    lowered = release_text.lower()
    for forbidden in ("pypi", "twine", "uv publish", "docker push", "docker/login-action"):
        assert forbidden not in lowered, f"Forbidden publication step in release.yml: {forbidden}"
