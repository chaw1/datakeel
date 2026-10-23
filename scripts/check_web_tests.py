# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require a render test for every page and feature directory."""

from pathlib import Path

from rich.console import Console


def violations() -> list[str]:
    """Check page test pairs and feature-level rendering coverage files."""
    problems: list[str] = []
    for page in Path("web/src/pages").glob("*.tsx"):
        if page.name.endswith(".test.tsx"):
            continue
        test = page.with_name(f"{page.stem}.test.tsx")
        if not test.is_file() or "render(" not in test.read_text():
            problems.append(f"{page}: missing matching render test {test.name}")
    problems.extend(
        f"{feature}: missing feature render test"
        for feature in Path("web/src/features").iterdir()
        if feature.is_dir()
        and not any(
            "render(" in test.read_text() or "renderHook(" in test.read_text()
            for test in feature.rglob("*.test.tsx")
        )
    )
    return problems


def main() -> None:
    """Fail when a page or feature has no executable rendering test."""
    problems = violations()
    Console().print("\n".join(problems) if problems else "Page and feature render tests present.")
    raise SystemExit(bool(problems))


if __name__ == "__main__":
    main()
