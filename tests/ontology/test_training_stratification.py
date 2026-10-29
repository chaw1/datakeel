# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Agent and MCP share typed source choices and handlers without database connections."""

import json
from typing import cast
from unittest.mock import MagicMock, patch

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.models import JsonDocument, utcnow
from datakeel.core.training_models import LeakageReport, SplitRequest, SplitSet
from datakeel.mcp.catalog import tool_definitions
from datakeel.ontology.training_functions import invoke_training
from datakeel.storage.database import Database


def test_mcp_training_schemas_offer_all_typed_annotation_sources() -> None:
    """Both discovered read tools carry the same nested policy enum and backwards default."""
    for tool in tool_definitions():
        if tool.name not in {"training_distribution", "training_leakage"}:
            continue
        schema = json.loads(tool.parameters.model_dump_json())
        assert schema["$defs"]["StratificationSource"]["enum"] == [
            "all",
            "classification",
            "detection",
            "spans",
        ]
        assert (
            schema["$defs"]["SplitRequest"]["properties"]["stratification_source"]["default"]
            == "all"
        )


def test_agent_and_mcp_handlers_forward_each_annotation_source() -> None:
    """The common function handler preserves caller policy for distribution and leakage previews."""
    database = cast("Database", MagicMock(spec=Database))
    access = AccessContext(actor="local-user", entry="agent", scope="query")
    for source in ("all", "classification", "detection", "spans"):
        request = SplitRequest(name="tools", stratification_source=source)
        split = SplitSet(
            id="split",
            dataset_id="dataset",
            version_id="version",
            request=request,
            members=(),
            distributions=(),
            created_at=utcnow(),
        )
        report = LeakageReport(
            split_set_id="split",
            dataset_id="dataset",
            version_id="version",
            sample_count=0,
            pairs=(),
        )
        arguments = JsonDocument(
            {
                "dataset_id": "dataset",
                "version_id": "version",
                "request": request.model_dump(mode="json"),
            }
        )
        for name, path, value in (
            ("training_distribution", "preview_split", split),
            ("training_leakage", "preview_leakage", report),
        ):
            with patch(
                f"datakeel.ontology.training_functions.{path}", return_value=value
            ) as reader:
                result = invoke_training(database, name, arguments, access)
            forwarded = reader.call_args.args[3]
            assert isinstance(forwarded, SplitRequest)
            assert forwarded.stratification_source == source
            assert result.function == name
