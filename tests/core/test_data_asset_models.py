# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Asset boundaries reject unsupported references, unknown fields and naive timestamps."""

import pytest
from pydantic import ValidationError

from datakeel.core.data_asset_models import AssetApplicationInput, DataAssetDefinition
from datakeel.core.models import AssetRef


@pytest.mark.parametrize(
    "target",
    [
        AssetRef(asset_type="file", asset_id="file"),
        AssetRef(asset_id="dataset", namespace="foreign"),
        AssetRef(asset_id=" "),
    ],
)
def test_definition_rejects_unsupported_resource_scope(target: AssetRef) -> None:
    """Only explicitly supported native objects can become published resources."""
    with pytest.raises(ValidationError):
        DataAssetDefinition(target=target, name="Generated", owner="Owner")


def test_definition_is_frozen_and_forbids_undeclared_fields() -> None:
    """External callers cannot mutate a validated definition or smuggle extra state."""
    definition = DataAssetDefinition(
        target=AssetRef(asset_id="dataset"), name="Generated", owner="Owner"
    )
    with pytest.raises(ValidationError, match="frozen"):
        definition.name = "Changed"
    with pytest.raises(ValidationError, match="Extra inputs"):
        DataAssetDefinition.model_validate({**definition.model_dump(), "secret": "undeclared"})


def test_application_requires_aware_expiry_and_explicit_scope() -> None:
    """Ambiguous local times and empty authorization scopes are rejected at ingress."""
    body = {
        "asset_id": "asset",
        "purpose": "Analysis",
        "scopes": ["query"],
        "expires_at": "2030-01-01T00:00:00",
    }
    with pytest.raises(ValidationError, match="timezone"):
        AssetApplicationInput.model_validate(body)
    with pytest.raises(ValidationError, match="at least 1"):
        AssetApplicationInput.model_validate(
            {**body, "scopes": [], "expires_at": "2030-01-01T00:00:00Z"}
        )
