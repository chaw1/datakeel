# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed knowledge bundles referenced by, never embedded in, lineage."""

import hashlib
import json
import tempfile
from pathlib import Path

from datakeel.core.errors import ValidationError
from datakeel.core.evidence_cache import KnowledgeBundle, KnowledgeBundleArtifact
from datakeel.core.models import AssetRef, LineageEvent
from datakeel.storage.objects import object_store


def publish_bundle(event: LineageEvent, bundle: KnowledgeBundle) -> LineageEvent:
    """Publish an immutable artifact and put only its reference in the COMPLETE event."""
    content = json.dumps(bundle.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    revision = hashlib.sha256(content.encode()).hexdigest()
    key = f"evidence/{revision[:2]}/{revision}.json"
    with tempfile.TemporaryDirectory(prefix="datakeel-evidence-") as temporary:
        path = Path(temporary) / "bundle.json"
        path.write_text(content, encoding="utf-8")
        object_store().put(path, key)
    artifact = KnowledgeBundleArtifact(object_key=key, content_revision=revision)
    return event.model_copy(
        update={
            "params": {
                **event.params,
                "run_id": bundle.run_id,
                "knowledge_bundle": artifact.model_dump(mode="json"),
            },
            "outputs": [ref for ref in event.outputs if ref.asset_type != "knowledge_bundle"]
            + [AssetRef(asset_type="knowledge_bundle", asset_id=revision, version="1.0")],
        }
    )


def load_bundle(event: LineageEvent) -> KnowledgeBundle:
    """Verify immutable artifact content before replaying any observation."""
    artifact = KnowledgeBundleArtifact.model_validate(event.params.get("knowledge_bundle"))
    content = object_store().materialize(artifact.object_key).read_bytes()
    if hashlib.sha256(content).hexdigest() != artifact.content_revision or not any(
        ref.asset_type == "knowledge_bundle" and ref.asset_id == artifact.content_revision
        for ref in event.outputs
    ):
        msg = "Knowledge bundle content hash or output reference does not match"
        raise ValidationError(msg)
    return KnowledgeBundle.model_validate_json(content)
