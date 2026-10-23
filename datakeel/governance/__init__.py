# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standard templates, metadata validation and explainable compliance."""

from datakeel.governance.compliance import compliance_score
from datakeel.governance.validation import DEFAULT_TEMPLATE, template_schema, validate_metadata

__all__ = ["DEFAULT_TEMPLATE", "compliance_score", "template_schema", "validate_metadata"]
