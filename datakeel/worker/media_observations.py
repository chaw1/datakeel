# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Project per-media-artifact lineage under the existing fenced shard transaction."""

from datakeel.core.media_models import MediaArtifactRecord
from datakeel.core.models import AssetRef, FileItem, LineageEvent
from datakeel.pipeline.models import PipelineObservation
from datakeel.storage.task_queue import Lease


def media_events(lease: Lease, value: PipelineObservation, node: AssetRef) -> list[LineageEvent]:
    """Link exact artifact identities to source files and versioned operator histories."""
    return [
        LineageEvent(
            idempotency_key=f"shard:{lease.shard_id}:node:{value.node_id}:file:{record.file_id}",
            operator=value.operator,
            source_module="worker",
            source_ref=lease.task_id,
            inputs=[node, AssetRef(asset_type="file", asset_id=record.source_file_id)],
            outputs=[
                AssetRef(asset_type="file", asset_id=record.file_id, display_name=record.filename)
            ],
            params={
                **value.params,
                "operator_version": "1.0.0",
                "source_asset_id": record.source_asset_id,
                "start_ms": record.start_ms,
                "end_ms": record.end_ms,
                "history": [step.model_dump(mode="json") for step in record.history],
            },
            quality={"input_count": 1, "output_count": 1},
        )
        for raw in value.quality.get("media_artifacts", [])
        for record in [MediaArtifactRecord.model_validate(raw)]
    ]


def published_media_events(
    events: list[LineageEvent], outputs: list[FileItem]
) -> list[LineageEvent]:
    """Publish file edges only for materialized manifest outputs, retaining node audits."""
    files = {file.id: file for file in outputs}
    result: list[LineageEvent] = []
    for event in events:
        if ":file:" not in event.idempotency_key:
            result.append(event)
            continue
        file = files.get(event.outputs[0].asset_id) if event.outputs else None
        if file is None:
            continue
        root = str(file.metadata["source_asset_id"])
        inputs = [ref for ref in event.inputs if ref.asset_type != "file"]
        inputs.append(AssetRef(asset_type="file", asset_id=root))
        result.append(
            event.model_copy(
                update={
                    "inputs": inputs,
                    "params": {
                        **event.params,
                        "immediate_source_file_id": file.metadata.get("source_file_id"),
                        "history": file.metadata.get("media_history", []),
                    },
                },
                deep=True,
            )
        )
    return result
