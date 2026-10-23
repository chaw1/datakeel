# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable exports using OpenLineage 2.0.2 and MLCommons Croissant 1.1.

References:
https://openlineage.io/spec/2-0-2/OpenLineage.json
https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html
Croissant vocabulary attribution: MLCommons Association and contributors.

"""

import mimetypes
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

from datakeel import __version__
from datakeel.core.models import AssetRef, FileItem, JsonDocument, LineageEvent, Record

OPENLINEAGE_SCHEMA = "https://openlineage.io/spec/2-0-2/OpenLineage.json"
PRODUCER = f"urn:datakeel:{__version__}"


def _facet(values: dict[str, Any]) -> dict[str, Any]:
    return {"_producer": PRODUCER, "_schemaURL": OPENLINEAGE_SCHEMA + "#/$defs/BaseFacet", **values}


def _asset(asset: AssetRef) -> dict[str, Any]:
    return {
        "namespace": asset.namespace,
        "name": f"{asset.asset_type}/{asset.asset_id}",
        "facets": {"datakeel_asset": _facet(asset.model_dump(mode="json"))},
    }


def export_openlineage(events: list[LineageEvent]) -> list[JsonDocument]:
    """Export each stored observation with a deterministic globally unique run id."""
    state_map = {
        "COMPLETED": "COMPLETE",
        "FAILED": "FAIL",
        "CANCELLED": "ABORT",
        "RUNNING": "RUNNING",
        "STARTED": "START",
        "START": "START",
        "COMPLETE": "COMPLETE",
        "FAIL": "FAIL",
        "ABORT": "ABORT",
    }
    result: list[dict[str, Any]] = []
    for event in events:
        timestamp = event.occurred_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        outputs = [_asset(asset) for asset in event.outputs]
        for output in outputs:
            output["outputFacets"] = {"datakeel_quality": _facet({"metrics": event.quality})}
        result.append(
            {
                "eventTime": timestamp.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "eventType": state_map.get(event.run_state, "OTHER"),
                "producer": PRODUCER,
                "schemaURL": OPENLINEAGE_SCHEMA + "#/$defs/RunEvent",
                "run": {
                    "runId": str(uuid5(NAMESPACE_URL, f"urn:datakeel:event:{event.event_id}")),
                    "facets": {
                        "datakeel_execution": _facet(
                            {
                                "eventId": event.event_id,
                                "idempotencyKey": event.idempotency_key,
                                "eventType": event.event_type,
                                "onBehalfOf": event.on_behalf_of,
                                "sourceModule": event.source_module,
                                "sourceRef": event.source_ref,
                                "parameters": event.params,
                            }
                        )
                    },
                },
                "job": {"namespace": "datakeel", "name": event.operator},
                "inputs": [_asset(asset) for asset in event.inputs],
                "outputs": outputs,
            }
        )
    return [JsonDocument.model_validate(item) for item in result]


def export_croissant(dataset: dict[str, Any] | Record, files: list[FileItem]) -> JsonDocument:
    """Describe each unstructured file as one record with a resolvable content source."""
    metadata: dict[str, Any] = dataset.get("metadata") or {}
    base_url = str(dataset.get("base_url", "http://127.0.0.1:8765")).rstrip("/")
    dataset_id = str(dataset.get("id", "dataset"))
    name = str(dataset.get("name", dataset_id))
    creator = metadata.get("creator", dataset.get("creator"))
    if not creator:
        creator = {"@type": "Organization", "name": "Unspecified dataset creator"}
    elif isinstance(creator, str):
        creator = {"@type": "Organization", "name": creator}
    license_value = metadata.get("license", dataset.get("license"))
    if not license_value:
        license_value = {
            "@type": "CreativeWork",
            "name": "License not supplied; no reuse permission is inferred.",
        }
    elif isinstance(license_value, str) and ":" not in license_value:
        license_value = {"@type": "CreativeWork", "name": license_value}
    publication = (
        metadata.get("datePublished")
        or dataset.get("created_at")
        or datetime.now(UTC).date().isoformat()
    )
    if isinstance(publication, int | float) and not isinstance(publication, bool):
        publication = datetime.fromtimestamp(publication, UTC).isoformat()
    elif isinstance(publication, date | datetime):
        publication = publication.isoformat()
    context = _context()
    distribution, records = _records(files, base_url, dataset_id)
    return JsonDocument.model_validate(
        {
            "@context": context,
            "@type": "sc:Dataset",
            "@id": "datasets/" + quote(dataset_id, safe=""),
            "name": name,
            "description": metadata.get("description", dataset.get("description"))
            or f"Manifest export for {name}; {len(files)} files.",
            "conformsTo": "http://mlcommons.org/croissant/1.1",
            "license": license_value,
            "creator": creator,
            "datePublished": str(publication),
            "url": dataset.get("url", f"{base_url}/api/datasets/{quote(dataset_id, safe='')}"),
            "version": str(dataset.get("version", dataset.get("latest_version", "1"))),
            "distribution": distribution,
            "recordSet": records,
        }
    )


def _context() -> dict[str, Any]:
    return {
        "@vocab": "http://schema.org/",
        "sc": "http://schema.org/",
        "cr": "http://mlcommons.org/croissant/",
        "dct": "http://purl.org/dc/terms/",
        "conformsTo": "dct:conformsTo",
        "recordSet": "cr:recordSet",
        "field": "cr:field",
        "source": "cr:source",
        "fileObject": "cr:fileObject",
        "extract": "cr:extract",
        "fileProperty": "cr:fileProperty",
        "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    }


def _records(
    files: list[FileItem], base_url: str, dataset_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    distribution: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for file in files:
        resource_id = "files/" + quote(file.id, safe="")
        record_id = "records/" + quote(file.id, safe="")
        resource: dict[str, Any] = {
            "@type": "cr:FileObject",
            "@id": resource_id,
            "name": file.filename,
            "contentUrl": (
                f"{base_url}/api/datasets/{quote(dataset_id, safe='')}/files/"
                f"{quote(file.id, safe='')}/download"
            ),
            "contentSize": f"{file.size} B",
            "encodingFormat": mimetypes.guess_type(file.filename)[0] or "application/octet-stream",
        }
        if file.sha256:
            resource["sha256"] = file.sha256
        distribution.append(resource)
        records.append(
            {
                "@type": "cr:RecordSet",
                "@id": record_id,
                "name": file.filename,
                "description": "One record containing this manifest file.",
                "field": [
                    {
                        "@type": "cr:Field",
                        "@id": record_id + "/content",
                        "name": "content",
                        "dataType": "sc:ImageObject"
                        if file.modality == "image"
                        else "sc:Text"
                        if file.modality == "text"
                        else "sc:MediaObject",
                        "source": {
                            "fileObject": {"@id": resource_id},
                            "extract": {"fileProperty": "content"},
                        },
                    }
                ],
            }
        )
    return distribution, records
