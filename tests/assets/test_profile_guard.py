# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Sensor-profile answers disclose dataset measurements only to callers allowed to read them."""

from pathlib import Path

import pytest

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.data_asset_models import AccessContext, AssetUsageQuery
from datakeel.core.errors import AuthorizationError
from datakeel.core.models import AssetRef
from datakeel.storage.data_asset_access import list_usage
from datakeel.storage.database import Database
from tests.ask.profile_helpers import SENSOR_QUESTION, publish_sensors
from tests.assets.entry_helpers import grant, publish

CALLER = AccessContext(actor="local", entry="ask", scope="query")


def test_profile_answer_for_restricted_dataset_requires_a_query_grant(
    db: Database, tmp_path: Path
) -> None:
    """Gap rankings come from the dataset itself, so its asset policy guards them."""
    dataset = publish_sensors(db, tmp_path / "sources")
    asset = publish(db, AssetRef(asset_id=dataset.dataset_id))
    with pytest.raises(AuthorizationError, match="apply for access"):
        ask_data(db, AskRequest(question=SENSOR_QUESTION), access=CALLER)
    assert list_usage(db, AssetUsageQuery()) == ()
    grant_id = grant(db, asset, "valid", "query")
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION), access=CALLER)
    assert answer.answer_kind == "profile"
    assert answer.status == "answered"
    usages = list_usage(db, AssetUsageQuery())
    assert [usage.grant_id for usage in usages] == [grant_id]


def test_profile_answer_for_public_dataset_needs_no_grant(db: Database, tmp_path: Path) -> None:
    """Public cards keep profile questions answerable while still auditing the read."""
    dataset = publish_sensors(db, tmp_path / "sources")
    publish(db, AssetRef(asset_id=dataset.dataset_id), "public")
    answer = ask_data(db, AskRequest(question=SENSOR_QUESTION), access=CALLER)
    assert answer.status == "answered"
    assert answer.profile is not None
    assert answer.profile.dataset == dataset
    assert len(list_usage(db, AssetUsageQuery())) == 1
