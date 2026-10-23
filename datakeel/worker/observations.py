# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build lineage observations for concurrent pipeline operator callbacks."""

import threading

from datakeel.core.models import AssetRef, LineageEvent
from datakeel.pipeline import Node, Pipeline, PipelineObservation
from datakeel.storage.task_queue import Lease


class Observations:
    """Collect typed lineage events with immutable upstream asset identities."""

    def __init__(self, lease: Lease, definition: Pipeline) -> None:
        """Index a validated pipeline and bind its leased execution identity."""
        self.lease = lease
        self.source = AssetRef(asset_id=lease.dataset_id)
        self.nodes = {node.id: node for node in definition.nodes}
        self.events: list[LineageEvent] = []
        self.lock = threading.Lock()

    def ancestors(self, reference: str) -> list[AssetRef]:
        """Resolve routing nodes to their nearest upstream producing assets."""
        identifier = reference.split(".", 1)[0]
        if identifier == "$input":
            return [self.source]
        node = self.nodes[identifier]
        if node.kind == "operator":
            return [self._artifact(node)]
        return [ref for upstream in node.inputs.values() for ref in self.ancestors(upstream)]

    def _artifact(self, node: Node) -> AssetRef:
        return AssetRef(
            asset_type="artifact",
            asset_id=f"{self.lease.shard_id}:{node.id}",
            display_name=node.operator,
        )

    def observe(self, value: PipelineObservation) -> None:
        """Capture one JSON operator observation in the append-only event shape."""
        if value.operator.startswith("evidence.") and value.run_state == "COMPLETED":
            return
        with self.lock:
            identifier = str(value.get("node_id", value["operator"]))
            node = self.nodes[identifier]
            upstream: dict[str, AssetRef] = {}
            for reference in node.inputs.values():
                for ref in self.ancestors(reference):
                    upstream[ref.asset_id] = ref
            self.events.append(
                LineageEvent(
                    idempotency_key=f"shard:{self.lease.shard_id}:node:{identifier}",
                    inputs=list(upstream.values()) or [self.source],
                    outputs=[self._artifact(node)] if value.run_state == "COMPLETED" else [],
                    operator=value["operator"],
                    source_ref=self.lease.task_id,
                    run_state=value.get("run_state", "COMPLETED"),
                    params=value.get("params", {}),
                    quality={
                        **value.get("quality", {}),
                        "input_count": value.get("input_count", 0),
                        "output_count": value.get("output_count", 0),
                    },
                )
            )
