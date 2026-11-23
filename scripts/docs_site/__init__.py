# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Static documentation and landing-page generator for GitHub Pages."""

from scripts.docs_site.build import build_site
from scripts.docs_site.models import BuildSummary, SiteConfig

__all__ = ["BuildSummary", "SiteConfig", "build_site"]
