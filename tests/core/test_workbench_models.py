# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Workbench boundary snapshots reject extra fields and retain the caller's server authority."""

import pytest
from pydantic import ValidationError

from datakeel.core.identity_models import EffectiveScopes
from datakeel.core.production_catalog_models import ProductionTemplate
from datakeel.core.workbench_models import WorkbenchIndex, WorkbenchTaskRisk


def test_workbench_index_is_frozen_and_rejects_unknown_fields() -> None:
    """HTTP views cannot accept accidental private data or mutate a frozen role projection."""
    index = WorkbenchIndex(
        actor="local",
        zero_users=True,
        effective_scopes=EffectiveScopes(actor="local", scopes=("*",), zero_users=True),
        projects=(),
    )
    assert WorkbenchIndex.model_validate_json(index.model_dump_json()) == index
    with pytest.raises(ValidationError):
        WorkbenchIndex.model_validate({**index.model_dump(), "private_path": "forbidden"})
    with pytest.raises(ValidationError):
        index.actor = "other"
    with pytest.raises(ValidationError):
        WorkbenchTaskRisk(task_id="task", prelabel_difference=1.1)


@pytest.mark.parametrize("components", [[], ["box", "box"], ["keypoints"], ["unknown"], "box"])
def test_template_component_lists_are_explicit_supported_and_distinct(components: object) -> None:
    """Unsupported configurations fail before approval rather than bypassing content validation."""
    with pytest.raises(ValidationError, match="distinct supported"):
        ProductionTemplate.model_validate(
            {"id": "mixed", "name": "Mixed", "component_config": {"components": components}}
        )
