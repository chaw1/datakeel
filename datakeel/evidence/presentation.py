# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Turn immutable object projections and observations into public sample evidence."""

from urllib.parse import quote

from datakeel.core.evidence_models import Assertion, EvidenceValue, ImageRegion, TextSpan
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.evidence.query_models import (
    EvidenceBox,
    EvidenceExplanation,
    EvidenceSample,
    EvidenceState,
    NearDuplicateCandidate,
)
from datakeel.ontology.models import FrozenObject


def _spans(assertions: list[Assertion]) -> list[TextSpan]:
    values = {
        (anchor.selector.start, anchor.selector.end)
        for assertion in assertions
        if assertion.predicate == "mentions"
        for anchor in assertion.anchors
        if isinstance(anchor.selector, TextSpan)
    }
    return [TextSpan(start=start, end=end) for start, end in sorted(values)]


def _boxes(assertions: list[Assertion]) -> list[EvidenceBox]:
    values = {
        (
            assertion.object.concept,
            anchor.selector.bbox,
            anchor.selector.width,
            anchor.selector.height,
        )
        for assertion in assertions
        if assertion.predicate == "annotated_as"
        and isinstance(assertion.object, EvidenceValue)
        and assertion.object.concept
        for anchor in assertion.anchors
        if isinstance(anchor.selector, ImageRegion)
    }
    return [
        EvidenceBox(concept=concept, bbox=bbox, width=width, height=height)
        for concept, bbox, width, height in sorted(values)
    ]


def _neighbors(ref: AssetRef, assertions: list[Assertion]) -> list[NearDuplicateCandidate]:
    result: list[NearDuplicateCandidate] = []
    for assertion in assertions:
        if not isinstance(assertion.object, AssetRef) or assertion.distance is None:
            continue
        other = (
            assertion.object if assertion.subject.asset_id == ref.asset_id else assertion.subject
        )
        result.append(
            NearDuplicateCandidate(
                asset_ref=other,
                distance=assertion.distance,
                reason=assertion.reason or "Direct perceptual-hash pair",
                assertion_id=assertion.id,
            )
        )
    return sorted(result, key=lambda value: (value.distance, value.asset_ref.asset_id))


def present_sample(value: FrozenObject, assertions: list[Assertion]) -> EvidenceSample:
    """Build sample evidence entirely from source facts and reviewed assertion projections."""
    properties = value.properties
    metadata = JsonDocument.model_validate(properties.get("metadata", {})).root
    caption, split = metadata.get("caption_text"), metadata.get("split")
    width, height = metadata.get("width"), metadata.get("height")
    dataset_id, quality = str(properties["dataset_id"]), properties["quality"]
    url = (
        f"/api/datasets/{quote(dataset_id, safe='')}/files/"
        f"{quote(value.asset_ref.asset_id, safe='')}/download"
        f"?version={quote(value.asset_ref.version or '', safe='')}"
    )
    return EvidenceSample(
        asset_ref=value.asset_ref,
        dataset_id=dataset_id,
        source_version=value.asset_ref.version or "",
        filename=str(properties["filename"]),
        split=split if split in ("train", "val") else None,
        thumbnail_url=None
        if metadata.get("corrupt") or properties.get("modality") != "image"
        else url,
        caption=caption if isinstance(caption, str) else None,
        caption_spans=_spans(assertions),
        annotation_boxes=_boxes(assertions),
        assertions=assertions,
        quality_score=float(quality) if isinstance(quality, int | float) else 0,
        near_duplicates=_neighbors(value.asset_ref, assertions),
        quarantined=properties.get("quarantined") is True,
        deleted=properties.get("deleted") is True,
        image_width=width if isinstance(width, int) else None,
        image_height=height if isinstance(height, int) else None,
    )


def explain(sample: EvidenceSample) -> EvidenceExplanation:
    """Explain observed states literally, preserving unknown and missing-assertion diagnostics."""
    states = [
        EvidenceState(
            predicate=assertion.predicate,
            concept=assertion.object.concept,
            value=assertion.object.value,
            status=assertion.status,
            reason=assertion.reason,
        )
        for assertion in sample.assertions
        if isinstance(assertion.object, EvidenceValue)
    ]
    names = {"present": "已观察到", "absent": "测量确认不存在", "unknown": "未知, 证据不足"}
    lines = [f"样本 {sample.filename}, 来源版本 {sample.source_version}。"]
    lines.extend(
        f"{state.predicate} {state.concept or ''}: {names[state.value]} "
        f"({state.value}; {state.status})。{state.reason or ''}"
        for state in states
    )
    if not sample.assertions:
        lines.append("尚无抽取断言; 请先运行证据抽取, 不能据此推断存在或不存在。")
    lines.extend(
        f"近重复候选 {candidate.asset_ref.asset_id}, 直接汉明距离 {candidate.distance}。"
        for candidate in sample.near_duplicates
    )
    return EvidenceExplanation(
        asset_ref=sample.asset_ref,
        text="\n".join(lines),
        assertions=sample.assertions,
        states=states,
    )
