# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Label one task image with a cloud model: views, requests, parsing, confidence and cost."""

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import NamedTuple

import httpx
from PIL import Image

from datakeel.annotation_qa import agreements, object_confidence
from datakeel.core.annotation_models import AnnotationBox, AnnotationRecord
from datakeel.core.prelabel_models import CloudModelConfig, PrelabelCall, PrelabelDrop
from datakeel.core.production_catalog_models import ParsedPrediction, ProductionModel
from datakeel.prelabel import (
    ParsedReply,
    ProviderReply,
    SentImage,
    call_input_tokens,
    encode_view,
    parse_reply,
    prelabel_prompt,
    request_view,
    token_cost,
)
from datakeel.storage.production_task_images import sample_image

FAILURE_MESSAGES = {
    "timeout": "The provider did not answer before the configured timeout",
    "rate_limited": "The provider rejected the request as rate limited (HTTP 429)",
    "network_error": "The provider could not be reached",
    "invalid_response": "The provider reply was not the requested JSON",
    "image_unreadable": "The task image could not be decoded",
}


class CloudRequest(NamedTuple):
    """Everything fixed for a run: model, kinds, label lookup, prompt and credential."""

    model: ProductionModel
    config: CloudModelConfig
    kinds: frozenset[str]
    lookup: dict[str, str]
    prompt: str
    api_key: str
    single_label: bool = False


class ImageOutcome(NamedTuple):
    """One image's calls and drops, plus either a draft or a failure code."""

    calls: tuple[PrelabelCall, ...]
    drops: tuple[PrelabelDrop, ...]
    prediction: ParsedPrediction | None
    failure: str | None

    @property
    def cost(self) -> Decimal:
        """Sum the measured cost of every call made for this image."""
        return sum((Decimal(str(call.cost)) for call in self.calls), Decimal(0))


def cloud_request(
    model: ProductionModel,
    kinds: frozenset[str],
    labels: dict[str, str],
    api_key: str,
    *,
    single_label: bool = False,
) -> CloudRequest:
    """Freeze a run's request settings; ``labels`` maps label ids to display names."""
    if model.cloud is None:
        message = "Cloud requests need a cloud model"
        raise ValueError(message)
    lookup = {
        value.casefold(): identifier
        for identifier, name in labels.items()
        for value in (identifier, name)
    }
    prompt = prelabel_prompt(
        tuple(labels.values()), kinds, model.cloud.coordinate_space, single_label=single_label
    )
    return CloudRequest(model, model.cloud, kinds, lookup, prompt, api_key, single_label)


def _call(
    request: CloudRequest, sample_id: str, view: SentImage, reply: ProviderReply
) -> PrelabelCall:
    config = request.config
    input_tokens, output_tokens = reply.input_tokens, reply.output_tokens
    if reply.failure is None and not reply.usage_reported:
        input_tokens = call_input_tokens(config, view.width, view.height)
        output_tokens = config.expected_output_tokens
    return PrelabelCall(
        sample_id=sample_id,
        view="mirrored" if view.mirrored else "primary",
        outcome="failed" if reply.failure else "ok",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=float(token_cost(config, input_tokens, output_tokens)),
        elapsed_seconds=reply.elapsed_seconds,
    )


def _draft(
    request: CloudRequest,
    sample_id: str,
    size: tuple[int, int],
    primary: ParsedReply,
    mirrored: ParsedReply | None,
) -> ParsedPrediction:
    source = request.config.confidence_source if request.config.cross_check else "self"
    confidences: list[float] = []
    labels: tuple[str, ...] | None = None
    if "classification" in request.kinds:
        labels = (primary.labels or ())[: 1 if request.single_label else None]
        if labels:
            agree = None if mirrored is None else float(set(mirrored.labels or ()) == set(labels))
            confidences.append(object_confidence(primary.labels_confidence, agree, source))
    boxes: tuple[AnnotationBox, ...] | None = None
    if "box" in request.kinds:
        found = [(item.label, item.box) for item in primary.objects]
        checks = (
            agreements(found, [(item.label, item.box) for item in mirrored.objects])
            if mirrored
            else None
        )
        boxes = tuple(
            AnnotationBox(
                category=item.label, x1=item.box[0], y1=item.box[1], x2=item.box[2], y2=item.box[3]
            )
            for item in primary.objects
        )
        confidences.extend(
            object_confidence(item.confidence, checks[index] if checks else None, source)
            for index, item in enumerate(primary.objects)
        )
    return ParsedPrediction(
        filename=sample_id,
        annotation=AnnotationRecord(
            sample_id=sample_id,
            annotator_id=request.model.name,
            labels=labels,
            boxes=boxes,
            image_width=size[0],
            image_height=size[1],
        ),
        confidence=round(sum(confidences) / len(confidences), 6) if confidences else 0.0,
        object_confidences=tuple(confidences),
    )


def _views(request: CloudRequest, image: Image.Image) -> list[SentImage]:
    side = request.config.max_image_side
    views = [encode_view(image, side)]
    if request.config.cross_check:
        views.append(encode_view(image, side, mirrored=True))
    return views


def label_image(
    request: CloudRequest, sample_id: str, key: str | None, client: httpx.Client
) -> ImageOutcome:
    """Send every view in parallel; a failed or unparseable primary view fails the image."""
    if key is None:
        return ImageOutcome((), (), None, "image_unreadable")
    try:
        with sample_image(key) as image:
            views, size = _views(request, image), (image.width, image.height)
    except (OSError, ValueError, Image.DecompressionBombError):
        return ImageOutcome((), (), None, "image_unreadable")

    def send(view: SentImage) -> ProviderReply:
        return request_view(request.config, view, request.prompt, client, request.api_key)

    with ThreadPoolExecutor(max_workers=len(views)) as pool:
        replies = list(pool.map(send, views))
    calls = tuple(
        _call(request, sample_id, view, reply) for view, reply in zip(views, replies, strict=True)
    )
    space = request.config.coordinate_space
    parsed = [
        parse_reply(reply.text, view, request.lookup, space) if reply.failure is None else None
        for view, reply in zip(views, replies, strict=True)
    ]
    primary = parsed[0]
    if primary is None:
        return ImageOutcome(calls, (), None, replies[0].failure or "invalid_response")
    drops = tuple(
        PrelabelDrop(sample_id=sample_id, reason=reason, detail=detail)  # type: ignore[arg-type]
        for reason, detail in primary.drops
    )
    mirrored = parsed[1] if len(parsed) > 1 else None
    return ImageOutcome(calls, drops, _draft(request, sample_id, size, primary, mirrored), None)
