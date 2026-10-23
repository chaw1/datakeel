# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reproducible synthetic evidence fixtures shipped with the demo package."""

from datakeel.sample_evidence.generator import generate_samples
from datakeel.sample_evidence.models import SampleGold

__all__ = ["SampleGold", "generate_samples"]
