# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recognize explicit sensor-gap questions and rank immutable recorded measurements."""

import re
from collections import defaultdict

from pydantic import ValidationError as ModelValidationError

from datakeel.core.ask_models import AskAnswer, AskRequest, MatchEvidence
from datakeel.core.models import BoundaryModel, new_id
from datakeel.core.profile_models import (
    DeviceGapRank,
    GapSort,
    ProfileAnswer,
    ProfileDataset,
    ProfileGapEvidence,
    PublishedProfile,
)


class ProfileQuestion(BoundaryModel):
    """Bind a narrow supported question to its exact matched sampling-gap phrase."""

    sort_by: GapSort
    requested_column: str | None = None
    match_start: int
    match_end: int


def parse_profile_question(request: AskRequest) -> ProfileQuestion | None:
    """Select only explicit device-gap rankings, preserving metric and knowledge intents."""
    if request.metric_id is not None or request.knowledge_intent is not None:
        return None
    question = request.question
    gap = re.search(r"断档|\bgaps?\b", question, re.IGNORECASE)
    ranking = re.search(r"最多|最长|最久|\b(?:most|longest|largest)\b", question, re.IGNORECASE)
    subject = re.search(
        r"设备|传感器|温度|\b(?:devices?|sensors?|temperature)\b", question, re.IGNORECASE
    )
    if gap is None or ranking is None or subject is None:
        return None
    count = re.search(r"次数|区间数|\bmost\b", question, re.IGNORECASE)
    duration = re.search(
        r"时长|最长|最久|\b(?:longest|duration|missing\s+time)\b", question, re.IGNORECASE
    )
    requested = (
        "temperature" if re.search(r"温度|\btemperature\b", question, re.IGNORECASE) else None
    )
    return ProfileQuestion(
        sort_by="gap_count" if count and not duration else "total_gap_ms",
        requested_column=requested,
        match_start=gap.start(),
        match_end=gap.end(),
    )


def _datasets(sources: tuple[PublishedProfile, ...]) -> tuple[ProfileDataset, ...]:
    values = {source.dataset.dataset_id: source.dataset for source in sources}
    return tuple(values[key] for key in sorted(values))


def _matches_column(source: PublishedProfile, requested: str) -> bool:
    names = {name.casefold() for name in source.columns}
    aliases = {"temperature", "温度"} if requested == "temperature" else {requested.casefold()}
    return bool(names & aliases)


def _ranking(sources: tuple[PublishedProfile, ...], sort_by: GapSort) -> tuple[DeviceGapRank, ...]:
    groups: dict[str, list[ProfileGapEvidence]] = defaultdict(list)
    for source in sources:
        for interval in source.gaps:
            groups[interval.device].append(interval)
    ranks = [
        DeviceGapRank(
            device=device,
            interval_count=len(intervals),
            total_gap_ms=sum(item.gap_ms for item in intervals),
            evidence=tuple(
                sorted(intervals, key=lambda item: (item.file_id, item.start_ms, item.rows))
            ),
        )
        for device, intervals in groups.items()
    ]
    return tuple(
        sorted(
            ranks,
            key=lambda item: (
                -(item.interval_count if sort_by == "gap_count" else item.total_gap_ms),
                -item.total_gap_ms,
                item.device,
            ),
        )
    )


def _resolved_measurements(
    base: ProfileAnswer,
    sources: tuple[PublishedProfile, ...],
    selected: ProfileDataset,
) -> ProfileAnswer:
    if any(not item.valid or not item.has_gap_summary for item in sources):
        return base.model_copy(update={"reason_code": "incomplete_profile", "dataset": selected})
    try:
        ranks = _ranking(sources, base.sort_by)
    except ModelValidationError:
        return base.model_copy(update={"reason_code": "incomplete_profile", "dataset": selected})
    return base.model_copy(
        update={
            "dataset": selected,
            "ranking": ranks,
            "reason_code": None if ranks else "no_recorded_gaps",
        }
    )


def _measurements(
    request: AskRequest,
    parsed: ProfileQuestion,
    sources: tuple[PublishedProfile, ...],
) -> ProfileAnswer:
    base = ProfileAnswer(sort_by=parsed.sort_by, requested_column=parsed.requested_column)
    if request.subject_id is not None:
        sources = tuple(item for item in sources if item.dataset.dataset_id == request.subject_id)
        if not sources:
            return base.model_copy(update={"reason_code": "unknown_subject"})
    if not sources:
        return base.model_copy(update={"reason_code": "no_profile"})
    if parsed.requested_column:
        sources = tuple(
            item
            for item in sources
            if not item.valid or _matches_column(item, parsed.requested_column)
        )
        if not sources:
            return base.model_copy(update={"reason_code": "unknown_column"})
    candidates = _datasets(sources)
    if len(candidates) > 1:
        return base.model_copy(
            update={
                "reason_code": "ambiguous_dataset",
                "candidates": candidates,
            }
        )
    selected = next(iter(candidates))
    return _resolved_measurements(base, sources, selected)


def _message(profile: ProfileAnswer, *, chinese: bool) -> str:
    if profile.reason_code is not None:
        messages = {
            "no_profile": (
                "没有已发布的时序剖析元数据。",
                "No published time-series profile is available.",
            ),
            "unknown_subject": (
                "所选数据集没有当前剖析记录。",
                "The selected dataset has no current profile.",
            ),
            "unknown_column": (
                "当前剖析未登记所问的温度列。",
                "No current profile records the requested temperature column.",
            ),
            "ambiguous_dataset": (
                "有多个数据集, 请选择本题的数据集。",
                "Choose one dataset before comparing its devices.",
            ),
            "incomplete_profile": (
                "当前版本的断档剖析不完整, 无法可靠排名。",
                "Current gap measurements are incomplete; devices cannot be ranked reliably.",
            ),
            "no_recorded_gaps": (
                "当前版本未记录可供排名的设备断档区间。",
                "No device gap intervals are recorded in the current version.",
            ),
        }
        return messages[profile.reason_code][0 if chinese else 1]
    measure = "断档区间数" if profile.sort_by == "gap_count" else "断档总时长"
    if chinese:
        return (
            f"按已发布版本的采样时间轴{measure}排序; 仅比较有已记录断档的设备。"
            "同表中的温度列不代表温度独有的缺值。"
        )
    measure_en = (
        "gap interval count" if profile.sort_by == "gap_count" else "total missing duration"
    )
    return (
        f"Ranked by sampling-axis {measure_en} in the published version. "
        "Only devices with recorded gaps are compared. "
        "A table containing temperature does not establish temperature-only missing values."
    )


def profile_answer(
    request: AskRequest,
    parsed: ProfileQuestion,
    sources: tuple[PublishedProfile, ...],
) -> AskAnswer:
    """Answer with recorded intervals, or return a value-free refusal or clarification."""
    profile = _measurements(request, parsed, sources)
    status = (
        "answered"
        if profile.ranking
        else ("clarification" if profile.reason_code == "ambiguous_dataset" else "unanswerable")
    )
    return AskAnswer(
        session_id=request.session_id or new_id(),
        question=request.question,
        reference_instant=request.reference_instant,
        answer_kind="profile",
        profile=profile,
        status=status,
        message=_message(profile, chinese=bool(re.search(r"[\u4e00-\u9fff]", request.question))),
        matches=(
            MatchEvidence(
                start=parsed.match_start,
                end=parsed.match_end,
                text=request.question[parsed.match_start : parsed.match_end],
                source="published_profile.sampling_gaps",
                match_kind="exact",
            ),
        ),
    )
