# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Preserve safe visual-provider diagnostics across CLI output and evaluation history."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.cli.kg_image_evaluation import evaluate
from datakeel.core.kg_image_request import ImageEvaluationRequest
from datakeel.core.transcription_models import TranscriptionResult
from datakeel.storage.kg_evaluations import get_evaluation
from datakeel.transcription.transport import request_transcription
from tests.kg.test_image_evaluation import external_case

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from datakeel.core.transcription_models import (
        ImageInput,
        TranscriptionMode,
        TranscriptionProfile,
    )
    from datakeel.storage.database import Database


class _MockVisual:
    def __init__(
        self, profile: TranscriptionProfile, client: httpx.Client, *, unsafe: bool
    ) -> None:
        self.profile, self.client, self.unsafe = profile, client, unsafe

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        ocr = TranscriptionResult(
            text="Generated local OCR", width=image.width, height=image.height, backend="ocr"
        )
        result = request_transcription(self.profile, image, ocr, self.client, "")
        return (
            result.model_copy(update={"error": "provider-body-must-stay-private"})
            if self.unsafe
            else result
        )


def _install_mock(monkeypatch: pytest.MonkeyPatch, *, unsafe: bool) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": "AllocationQuota.FreeTierOnly",
                    "message": "provider-body-must-stay-private",
                }
            },
        )

    @contextmanager
    def factory(profile: TranscriptionProfile) -> Generator[_MockVisual]:
        with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as client:
            yield _MockVisual(profile, client, unsafe=unsafe)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("The mocked evaluation must not read model credentials")

    monkeypatch.setattr("datakeel.cli.kg_image_evaluation.create_transcriber", factory)
    monkeypatch.setattr("datakeel.transcription.factory.get_settings", forbidden)
    monkeypatch.setattr("datakeel.extraction_runtime.factory.get_settings", forbidden)
    return requests


@pytest.mark.parametrize(("json_output", "unsafe"), [(False, False), (True, False), (True, True)])
def test_visual_quota_message_survives_cli_and_history_without_provider_body(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    json_output: bool,
    unsafe: bool,
) -> None:
    """Both CLI formats keep the canonical failure and only the exact public quota diagnostic."""
    external_case(tmp_path)
    requests = _install_mock(monkeypatch, unsafe=unsafe)
    report = evaluate(
        db,
        ImageEvaluationRequest(cases=tmp_path, transcription_profile="bailian-qwen35-flash"),
        json_output=json_output,
    )
    output = capsys.readouterr().out
    expected = "服务商额度不足"
    assert len(requests) == 1
    assert report.failures[0].reason == "transcription:provider_quota_exhausted"
    assert report.failures[0].message == expected
    assert report.product.all.relation_strict.tp == 0
    assert get_evaluation(db, report.id) == report
    assert "provider-body-must-stay-private" not in output + report.model_dump_json()
    assert "AllocationQuota.FreeTierOnly" not in output + report.model_dump_json()
    if json_output:
        failure = json.loads(output)["failures"][0]
        assert failure["message"] == expected
    else:
        assert expected is not None
        assert expected in output
