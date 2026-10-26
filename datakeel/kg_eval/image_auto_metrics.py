# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure observed image decisions separately from independent routing expectations."""

from datakeel.core.kg_image_auto_eval import ImageAutoMetrics, ImageRouteResult
from datakeel.core.kg_image_eval import KGImageCase, KGImageSuite
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.kg_eval.image_execution import ImageCaseExecution
from datakeel.transcription.policy import is_external


def _observed_route(
    case: KGImageCase, execution: ImageCaseExecution | None, *, external: bool
) -> ImageRouteResult:
    if execution is None:
        return ImageRouteResult(case_id=case.id, expected_route=case.expected_route, route=None)
    transcript = execution.transcript
    decision = transcript.auto_decision
    route = decision.route if decision else transcript.mode
    return ImageRouteResult(
        case_id=case.id,
        expected_route=case.expected_route,
        route=route if route != "auto" else None,
        reasons=decision.reasons if decision else (),
        external=route == "vlm" and external,
    )


def auto_metrics(
    suite: KGImageSuite,
    executions: tuple[ImageCaseExecution, ...],
    profile: TranscriptionProfile,
    extraction_f1: float,
) -> ImageAutoMetrics | None:
    """Keep replay's simulated VLM fraction distinct from actual outbound image transfers."""
    if not any(case.expected_route for case in suite.cases):
        return None
    observed = {execution.raw.pid: execution for execution in executions}
    routes = tuple(
        _observed_route(case, observed.get(case.id), external=is_external(profile))
        for case in suite.cases
    )
    labelled = sum(item.expected_route is not None for item in routes)
    correct = sum(
        item.expected_route is not None and item.route == item.expected_route for item in routes
    )
    external = sum(item.external for item in routes)
    visual = sum(item.route == "vlm" for item in routes)
    return ImageAutoMetrics(
        cases=len(routes),
        labelled_cases=labelled,
        route_correct=correct,
        route_accuracy=round(correct / labelled, 3),
        external_images=external,
        external_ratio=round(external / max(len(routes), 1), 3),
        vlm_images=visual,
        vlm_ratio=round(visual / max(len(routes), 1), 3),
        extraction_f1=extraction_f1,
        routes=routes,
    )
