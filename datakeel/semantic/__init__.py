# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Contract based file semantics with conservative evidence resolution."""

import re
from copy import deepcopy
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, cast

from pydantic import JsonValue

from datakeel.core.errors import ValidationError
from datakeel.core.models import JsonDocument
from datakeel.semantic._snapshot import CONTRACT

if TYPE_CHECKING:
    from collections.abc import Callable


def validate_contract(contract: JsonDocument | dict[str, Any]) -> None:
    """Reject ambiguous format maps and equal priority role predicates."""
    contract = contract.root if isinstance(contract, JsonDocument) else contract
    codes: set[str] = set()
    extensions: set[str] = set()
    predicates: set[str] = set()
    for item in contract["formats"]:
        if item["code"] in codes:
            msg = f"Duplicate format code: {item['code']}"
            raise ValidationError(msg)
        codes.add(item["code"])
        if item["defaultModality"] not in contract["vocabularies"]["modality"]:
            msg = "Unknown modality"
            raise ValidationError(msg)
        for suffix in item["extensions"]:
            if suffix in extensions or suffix != suffix.lower() or suffix.startswith("."):
                msg = f"Invalid or duplicate extension: {suffix}"
                raise ValidationError(msg)
            extensions.add(suffix)
    for rule in contract["roleRules"]:
        key = f"{rule['priority']}:{sorted(rule['when'].items())}"
        if key in predicates:
            msg = "Role rules conflict at the same priority"
            raise ValidationError(msg)
        predicates.add(key)
    _validate_aliases(contract, codes)


def _validate_aliases(contract: dict[str, Any], codes: set[str]) -> None:
    aliases = {item["alias"]: item["target"] for item in contract.get("formatAliases", [])}
    for original_alias in aliases:
        alias = original_alias
        seen: set[str] = set()
        while alias in aliases:
            if alias in seen:
                msg = "Format alias cycle"
                raise ValidationError(msg)
            seen.add(alias)
            alias = aliases[alias]
        if alias not in codes:
            msg = "Format alias target is absent"
            raise ValidationError(msg)


validate_contract(CONTRACT)
FORMATS = {suffix: item for item in CONTRACT["formats"] for suffix in item["extensions"]}
SUFFIXES = sorted(FORMATS, key=len, reverse=True)


def get_contract() -> JsonDocument:
    """Copy the validated, extensible semantic-contract JSON boundary."""
    return JsonDocument.model_validate(deepcopy(CONTRACT))


def _suffix(filename: str) -> str | None:
    name = filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in SUFFIXES:
        if name.endswith("." + suffix) and len(name) > len(suffix) + 1:
            return suffix
    if "." not in name or (name.startswith(".") and name.count(".") == 1):
        return None
    return name.rsplit(".", 1)[1] or None


def _mime_conflicts(mime: str | None, item: dict[str, Any], suffix: str) -> bool:
    if not mime or mime in {"application/octet-stream", "binary/octet-stream"}:
        return False
    mime = mime.split(";", 1)[0].lower()
    if (
        mime in item["mimeHints"]
        or (mime in {"application/gzip", "application/x-gzip"} and suffix.endswith(("gz", "tgz")))
        or (mime == "application/x-bzip2" and suffix.endswith(("bz2", "tbz2")))
    ):
        return False
    modality = item["defaultModality"]
    if mime.startswith(("image/", "audio/", "video/")):
        return mime.split("/", 1)[0] != modality
    if mime.startswith("text/"):
        return modality not in {"text", "table"}
    known = {
        hint: fmt["defaultModality"] for fmt in CONTRACT["formats"] for hint in fmt["mimeHints"]
    }
    return mime in known and known[mime] != modality


def _matches(rule: dict[str, Any], context: dict[str, Any], code: str) -> bool:
    path = str(context.get("relativePath") or context["fileName"]).replace("\\", "/").lower()
    name = path.rsplit("/", 1)[-1]
    predicates: dict[str, Callable[[Any], bool]] = {
        "standardRole": lambda _: bool(context.get("standardRole")),
        "manifestRole": lambda _: bool(context.get("manifestRole")),
        "parentRelationAny": lambda value: context.get("parentRelation") in value,
        "pathPrefixAny": lambda value: any(path.startswith(prefix) for prefix in value),
        "pathSegmentsAny": lambda value: bool(set(value).intersection(path.split("/")[:-1])),
        "fileNameRegex": lambda value: bool(re.search(value, name)),
        "pathDepthMax": lambda value: len(PurePosixPath(path).parts) <= value,
        "fileNameSuffixAny": lambda value: any(name.endswith(suffix) for suffix in value),
        "formatCodesAny": lambda value: code in value,
        "datasetTypesNotAny": lambda value: context.get("datasetType") not in value,
    }
    return all(predicates[key](value) for key, value in rule["when"].items() if key in predicates)


def resolve(context: JsonDocument | dict[str, Any]) -> JsonDocument:
    """Resolve a validated extensible contract input into a JSON document."""
    validated = JsonDocument.model_validate(context)
    return JsonDocument.model_validate(_resolve(validated.model_dump()))


def _resolve(context: dict[str, Any]) -> dict[str, Any]:
    context = dict(context)
    for role_key in ["standardRole", "manifestRole"]:
        if isinstance(context.get(role_key), list) and len(context[role_key]) == 1:
            context[role_key] = context[role_key][0]
    filename = str(context.get("fileName") or "")
    suffix = _suffix(filename)
    item = FORMATS.get(suffix or "")
    raw = context.get("fileTypeRaw")
    result: dict[str, Any] = {
        "normalizedSuffix": suffix,
        "formatFamily": "unknown",
        "modality": "unknown",
        "usageRoleHint": None,
        "containerKind": "none",
        "confidence": 0,
        "ruleIdHint": "unknown.context-required.v1",
        "resolutionStatus": "unknown",
        "formatCode": item["code"] if item else "unknown",
        "admissionState": "quarantined",
    }
    if not suffix or item is None:
        return _unknown_result(context, result, suffix)
    raw_normalized = str(raw).lower().lstrip(".") if raw else None
    raw_conflict = raw_normalized is not None and raw_normalized != suffix
    if raw_conflict or _mime_conflicts(context.get("mime"), item, suffix):
        result.update(ruleIdHint="conflict.mime-extension.v1", resolutionStatus="ambiguous")
        if raw_conflict:
            result["conflicts"] = [f"fileName:{suffix}", f"fileTypeRaw:{raw_normalized}"]
        return result
    rule_id = item.get("ruleIds", {}).get(suffix) or item.get("ruleIdPattern", "").format(
        extension=suffix
    )
    result.update(
        formatFamily=item["formatFamily"],
        modality=item["defaultModality"],
        containerKind=item["containerKind"],
        ruleIdHint=rule_id,
    )
    if rule_id.startswith("unknown."):
        if item["formatFamily"] == "executable":
            result["admissionState"] = "rejected"
        return result
    result.update(
        usageRoleHint="payload",
        confidence=1,
        resolutionStatus="resolved",
        admissionState="accepted",
    )
    if suffix == "pcd.bin":
        path = str(context.get("relativePath") or filename).replace("\\", "/")
        result["provenance"] = [
            "suffix:bin",
            f"datasetType:{context.get('datasetType', 'unknown')}",
            f"path:{path.split('/')[0]}",
            "filename:*.pcd.bin",
        ]
    return _resolve_role(context, item, result)


def _unknown_result(
    context: dict[str, Any],
    result: dict[str, Any],
    suffix: str | None,
) -> dict[str, Any]:
    if not suffix and "fileTypeRaw" in context:
        raw = context["fileTypeRaw"]
        if raw is None:
            result["ruleIdHint"] = "unknown.missing-file-type.v1"
        elif raw == "":
            result["ruleIdHint"] = "unknown.empty-file-type.v1"
        elif not re.fullmatch(r"\.?[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*", str(raw)):
            result["ruleIdHint"] = "unknown.invalid-raw-file-type.v1"
    return result


def _resolve_role(
    context: dict[str, Any],
    item: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    for role_key in ["standardRole", "manifestRole"]:
        roles = context.get(role_key)
        if isinstance(roles, list) and len(set(cast("list[str]", roles))) > 1:
            result.update(
                usageRoleHint=None,
                confidence=0,
                resolutionStatus="ambiguous",
                admissionState="quarantined",
                ruleIdHint="conflict.role.same-priority.v1",
                conflicts=roles,
            )
            return result
    matches = [
        rule
        for rule in sorted(CONTRACT["roleRules"], key=lambda r: -r["priority"])
        if _matches(rule, context, item["code"])
    ]
    if matches:
        top = [rule for rule in matches if rule["priority"] == matches[0]["priority"]]
        roles = {rule["then"]["usageRole"] for rule in top}
        if len(roles) > 1:
            result.update(
                usageRoleHint=None,
                confidence=0,
                resolutionStatus="ambiguous",
                admissionState="quarantined",
                ruleIdHint="conflict.role.same-priority.v1",
                conflicts=sorted(roles),
            )
            return result
    for rule in matches:
        role = rule["then"]["usageRole"]
        rule_id = rule["id"]
        if role == "fromStandard":
            role = context["standardRole"]
            rule_id = f"role.{role}.standard.v1"
        elif role == "fromManifest":
            role = context["manifestRole"]
            rule_id = f"role.{role}.explicit-manifest.v1"
        if role not in CONTRACT["vocabularies"]["usageRole"]:
            result.update(resolutionStatus="ambiguous", admissionState="quarantined", confidence=0)
            return result
        result.update(usageRoleHint=role, confidence=rule["then"]["confidence"], ruleIdHint=rule_id)
        break
    return result


def classify(filename: str, **context: JsonValue) -> JsonDocument:
    """Add snake-case compatibility fields to one validated semantic result."""
    result = resolve({"fileName": filename, **context})
    return JsonDocument.model_validate(
        {
            **result.model_dump(),
            "format_code": result["formatCode"],
            "extension": result["normalizedSuffix"],
            "usage_role": result["usageRoleHint"],
            "container_kind": result["containerKind"],
            "admission_status": result["admissionState"],
        }
    )
