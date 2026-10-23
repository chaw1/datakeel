# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Open kind registration does not broaden the controlled frozen-selection boundary."""

import pytest

from datakeel.core import object_kinds
from datakeel.core.models import BoundaryModel
from datakeel.core.object_kinds import (
    object_property_model,
    register_object_kind,
    registered_object_kinds,
)
from datakeel.ontology.models import IdentityMapping, LinkType, ObjectSet
from datakeel.ontology.registry import object_definitions, register_object_type


def test_kind_when_registered_exposes_schema_and_validates_link_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One registry supplies property schemas and accepted link domain/range names."""
    monkeypatch.setattr(object_kinds, "_KINDS", dict.fromkeys(registered_object_kinds()))
    register_object_type("custom_kind", BoundaryModel)
    link = LinkType(
        id="custom",
        domain=["custom_kind"],
        range=["column"],
        cardinality="many-to-many",
        semantics="custom",
        description="Custom relationship",
    )
    assert link.domain == ["custom_kind"]
    assert object_property_model("custom_kind") is BoundaryModel
    assert any(item.id == "custom_kind" for item in object_definitions())
    assert IdentityMapping(asset_type="custom_kind").asset_type == "custom_kind"
    with pytest.raises(ValueError, match="frozen asset selections"):
        ObjectSet(object_type="custom_kind")


def test_kind_when_unknown_or_invalid_fails_at_load_time() -> None:
    """Reject unregistered kinds and malformed registration names immediately."""
    with pytest.raises(ValueError, match="Unregistered"):
        LinkType(
            id="invalid",
            domain=["absent_kind"],
            range=["column"],
            cardinality="many-to-many",
            semantics="invalid",
            description="Unknown relationship",
        )
    with pytest.raises(ValueError, match="Unregistered"):
        IdentityMapping(asset_type="absent_kind")
    with pytest.raises(ValueError, match="lowercase"):
        register_object_kind("Invalid / kind")
