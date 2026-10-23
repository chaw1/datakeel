# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Extract portable asset identities from typed tool arguments and results."""

from pydantic import JsonValue

from datakeel.core.models import AssetRef


def unique_refs(refs: list[AssetRef]) -> list[AssetRef]:
    """Keep versions and namespaces distinct while deduplicating repeated references."""
    values = {(ref.namespace, ref.asset_type, ref.asset_id, ref.version): ref for ref in refs}
    return list(values.values())


def reconcile_refs(authoritative: list[AssetRef], inferred: list[AssetRef]) -> list[AssetRef]:
    """Keep an inferred dataset fallback from contradicting a known catalog identity."""
    kinds: dict[tuple[str, str], set[str]] = {}
    for ref in authoritative:
        kinds.setdefault((ref.namespace, ref.asset_id), set()).add(ref.asset_type)
    selected = [
        ref
        for ref in inferred
        if ref.asset_type != "dataset"
        or "dataset" in kinds.get((ref.namespace, ref.asset_id), {"dataset"})
    ]
    return unique_refs(authoritative + selected)


def extract_refs(value: JsonValue, asset_type: str = "dataset") -> list[AssetRef]:
    """Recognize explicit AssetRefs and named identity parameters recursively."""
    refs: list[AssetRef] = []
    if isinstance(value, list):
        for item in value:
            refs.extend(extract_refs(item, asset_type))
    elif isinstance(value, dict):
        identifier = value.get("asset_id")
        if isinstance(identifier, str):
            kind, namespace, version = (
                value.get("asset_type", asset_type),
                value.get("namespace", "default"),
                value.get("version"),
            )
            refs.append(
                AssetRef(
                    asset_id=identifier,
                    asset_type=kind if isinstance(kind, str) else asset_type,
                    namespace=namespace if isinstance(namespace, str) else "default",
                    version=version if isinstance(version, str) else None,
                )
            )
        for key, item in value.items():
            if key == "version_ids" and isinstance(item, list):
                refs.extend(
                    AssetRef(asset_type="version", asset_id=version_id, version=version_id)
                    for version_id in item
                    if isinstance(version_id, str)
                )
            if key in {"dataset_id", "file_id", "version_id", "task_id"} and isinstance(item, str):
                refs.append(
                    AssetRef(
                        asset_type=key.removesuffix("_id"),
                        asset_id=item,
                        version=item if key == "version_id" else None,
                    )
                )
            refs.extend(extract_refs(item, asset_type))
    return unique_refs(refs)


def argument_refs(name: str, arguments: JsonValue) -> list[AssetRef]:
    """Resolve evidence asset_id arguments as files even when a read is rejected."""
    kind = "file" if name in {"get_evidence", "explain_sample"} else "dataset"
    return extract_refs(arguments, kind)
