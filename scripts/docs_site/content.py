# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load validated bilingual landing-page content from static/landing.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from scripts.docs_site.models import (
    ComparisonRow,
    FaqItem,
    LandingBundle,
    LanguageCode,
    LocalizedLanding,
    PillarItem,
)

_LANDING_YAML = Path(__file__).resolve().parent / "static/landing.yaml"


@lru_cache(maxsize=1)
def _load_bundle() -> LandingBundle:
    raw = yaml.safe_load(_LANDING_YAML.read_text(encoding="utf-8"))
    return LandingBundle.model_validate(raw)


def landing_for(lang: LanguageCode) -> LocalizedLanding:
    """Return the validated landing-page copy and structured blocks for a language."""
    bundle = _load_bundle()
    return bundle.zh if lang == "zh" else bundle.en


def pillars_for(lang: LanguageCode) -> tuple[PillarItem, ...]:
    """Return localized landing-page capability pillars."""
    return landing_for(lang).pillars


def comparison_for(lang: LanguageCode) -> tuple[ComparisonRow, ...]:
    """Return localized positioning comparison rows."""
    return landing_for(lang).comparison


def faq_for(lang: LanguageCode) -> tuple[FaqItem, ...]:
    """Return localized FAQ items."""
    return landing_for(lang).faq
