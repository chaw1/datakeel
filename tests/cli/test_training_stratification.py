# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The CLI forwards the shared typed annotation-source policy without database access."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from datakeel.cli import parser
from datakeel.cli.training import dispatch
from datakeel.core.models import utcnow
from datakeel.core.training_models import SplitRequest, SplitSet
from datakeel.storage.database import Database


def test_cli_forwards_each_annotation_source_to_named_split_creation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every declared source reaches the typed service; unknown sources fail during parsing."""
    for source in ("all", "classification", "detection", "spans"):
        request = SplitRequest(name="cli", stratification_source=source)
        result = SplitSet(
            id="split",
            dataset_id="dataset",
            version_id="version",
            request=request,
            members=(),
            distributions=(),
            created_at=utcnow(),
        )
        arguments = parser().parse_args(
            [
                "training",
                "create",
                "dataset",
                "--version",
                "version",
                "--name",
                "cli",
                "--stratification-source",
                source,
            ]
        )
        with patch("datakeel.cli.training.create_split", return_value=result) as create:
            dispatch(cast("Database", MagicMock(spec=Database)), arguments)
        forwarded = create.call_args.args[3]
        assert isinstance(forwarded, SplitRequest)
        assert forwarded.stratification_source == source
        assert SplitSet.model_validate_json(capsys.readouterr().out).request == request
    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "training",
                "create",
                "dataset",
                "--name",
                "invalid",
                "--stratification-source",
                "boxes",
            ]
        )
