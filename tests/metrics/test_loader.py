# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""YAML contracts reject malformed documents and ambiguous identities."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.metric_models import MetricFilter, SemanticLayer, TimeRange
from datakeel.metrics.loader import load_layer


def test_load_layer_directory_merges_typed_contracts(tmp_path: Path, layer: SemanticLayer) -> None:
    """Load three independently versioned YAML files into one semantic layer."""
    for key, value in layer.model_dump(mode="json").items():
        (tmp_path / f"{key}.yaml").write_text(yaml.safe_dump({key: value}))
    assert load_layer(tmp_path) == layer


@pytest.mark.parametrize("content", ["metrics: [", "unknown: true", "metrics: [{id: missing}]"])
def test_load_layer_invalid_document_reports_file(tmp_path: Path, content: str) -> None:
    """Surface parsing and schema failures rather than silently dropping definitions."""
    path = tmp_path / "broken.yaml"
    path.write_text(content)
    with pytest.raises(ValidationError, match=r"broken\.yaml"):
        load_layer(path)


def test_load_layer_missing_file_reports_reason(tmp_path: Path) -> None:
    """Missing contracts are actionable loader failures."""
    with pytest.raises(ValidationError, match=r"missing\.yaml"):
        load_layer(tmp_path / "missing.yaml")


def test_load_layer_duplicate_identity_is_rejected(tmp_path: Path, layer: SemanticLayer) -> None:
    """Merge order never chooses an arbitrary conflicting metric."""
    for name in ("first", "second"):
        (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump(layer.model_dump(mode="json")))
    with pytest.raises(ValidationError, match="Duplicate metric"):
        load_layer(tmp_path)


def test_filter_lists_and_time_ranges_validate_at_boundary() -> None:
    """Reject reversed time bounds and invalid membership value shapes."""
    with pytest.raises(ModelValidationError, match="in operator"):
        MetricFilter(column="x", op="in", value=1)
    with pytest.raises(ModelValidationError, match="in operator"):
        MetricFilter(column="x", value=[1])
    with pytest.raises(ModelValidationError, match="end must follow"):
        TimeRange.model_validate({"start": "2026-10-02", "end": "2026-10-01"})


def test_enterprise_contracts_load_with_required_catalog_size() -> None:
    """The shipped semantic fixtures meet the metric, dimension, and glossary minimums."""
    layer = load_layer(Path("contracts/semantic-layer"))
    assert len(layer.metrics) >= 12
    assert len(layer.dimensions) >= 6
    assert len(layer.terms) >= 30
