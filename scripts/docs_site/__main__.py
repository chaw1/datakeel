# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for building the Datakeel GitHub Pages site."""

from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from scripts.docs_site.build import build_site, read_package_version
from scripts.docs_site.models import SiteConfig

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Parse arguments and write the static documentation site."""
    parser = argparse.ArgumentParser(description="Build the Datakeel static documentation site.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/site",
        help="Destination directory for the generated static site.",
    )
    parser.add_argument(
        "--base-url",
        default="https://chaw1.github.io/datakeel/",
        help="Canonical public URL where the site will be hosted.",
    )
    parser.add_argument(
        "--repo-url",
        default="https://github.com/chaw1/datakeel",
        help="Canonical GitHub repository URL.",
    )
    args = parser.parse_args()
    config = SiteConfig(
        repo_root=ROOT,
        output_dir=args.output.resolve(),
        base_url=args.base_url,
        repo_url=args.repo_url,
        version=read_package_version(ROOT),
    )
    summary = build_site(config)
    Console().print(
        f"Built Datakeel site in {config.output_dir}: "
        f"{summary.pages_written} HTML pages ({summary.docs_written} docs), "
        f"{summary.assets_copied} assets, {summary.sitemap_urls} sitemap URLs."
    )


if __name__ == "__main__":
    main()
