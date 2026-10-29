# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Attach versioned media execution history and typed per-artifact observations."""

import hashlib
import json
from typing import TYPE_CHECKING, cast

from datakeel.core.media_models import MediaArtifactRecord, MediaStep
from datakeel.operators.media.isolation import has_failed

if TYPE_CHECKING:
    from pydantic import JsonValue

    from datakeel.core.models import FileItem
    from datakeel.operators.base import OperatorResult, Params


def record_media_result(
    result: "OperatorResult", operator: str, params: "Params"
) -> "OperatorResult":
    """Preserve every media operation in direct and queued operator execution."""
    from datakeel.operators.base import OperatorResult  # noqa: PLC0415  # Avoid registry cycle.

    parameters = cast("dict[str, JsonValue]", params.model_dump(mode="json"))
    digest = hashlib.sha256(json.dumps(parameters, sort_keys=True).encode()).hexdigest()
    files: list[FileItem] = []
    artifacts: list[MediaArtifactRecord] = []
    for file in result.files:
        if has_failed(file):
            files.append(file)
            continue
        history = [
            MediaStep.model_validate(step) for step in file.metadata.get("media_history", [])
        ]
        probe = file.metadata.get("media_probe", {})
        if (
            not history
            or history[-1].operator != operator
            or history[-1].parameters_digest != digest
        ):
            history.append(
                MediaStep(
                    operator=operator,
                    parameters=parameters,
                    parameters_digest=digest,
                    source_file_id=file.id,
                    end_ms=probe.get("duration_ms"),
                )
            )
        metadata = {
            **file.metadata,
            "media_history": [step.model_dump(mode="json") for step in history],
        }
        files.append(file.model_copy(update={"metadata": metadata}, deep=True))
        if file.metadata.get("source_file_id") and history[-1].source_file_id != file.id:
            artifacts.append(
                MediaArtifactRecord(
                    file_id=file.id,
                    filename=file.filename,
                    source_file_id=str(file.metadata["source_file_id"]),
                    source_asset_id=str(
                        file.metadata.get("source_asset_id", file.metadata["source_file_id"])
                    ),
                    start_ms=int(
                        file.metadata.get("source_start_ms", file.metadata.get("start_ms", 0))
                    ),
                    end_ms=file.metadata.get("source_end_ms", file.metadata.get("end_ms")),
                    history=history,
                )
            )
    return OperatorResult(
        files=files,
        quality={
            **result.quality,
            "media_artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        },
    )
