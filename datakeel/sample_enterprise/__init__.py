# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic fictional kitchen-appliance sources packaged with the demo."""

from datakeel.sample_enterprise.generator import generate_enterprise
from datakeel.sample_enterprise.models import EnterpriseGold, EnterpriseSample, SourceSample

__all__ = ["EnterpriseGold", "EnterpriseSample", "SourceSample", "generate_enterprise"]
