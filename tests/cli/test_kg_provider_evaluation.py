# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""An external case and YAML profile exercise actual model transport without any connection."""

import json
import socket
from contextlib import AbstractContextManager
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml
from pydantic import SecretStr

from datakeel.cli.kg_evaluation import evaluate
from datakeel.core.kg_contracts import ExtractionProfile
from datakeel.extraction_runtime import factory
from datakeel.kg.extractors import ExtractorAdapter
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces


def _inputs(directory: Path) -> tuple[Path, Path]:
    profile, cases = directory / "profile.yaml", directory / "cases.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "id": "mock-provider",
                "extractor": "llm",
                "provider": "openai",
                "model": "unpriced-fixture-model",
                "base_url": "https://fixture.invalid/v1",
                "api_key_env": "FIXTURE_KEY_NAME",
                "output_method": "json_schema",
                "chunk_size": 30,
                "chunk_overlap": 0,
            }
        )
    )
    cases.write_text(
        yaml.safe_dump(
            {
                "id": "external-fixture",
                "cases": [
                    {
                        "id": "outside-corpus",
                        "lang": "en",
                        "text": (
                            "Cafe\u0301 is nearby. Mira owns SignalBoard. Mira owns SignalBoard."
                        ),
                        "entities": [
                            {"name": "Mira", "type": "person"},
                            {"name": "SignalBoard", "type": "system"},
                        ],
                        "relations": [{"head": "Mira", "relation": "owns", "tail": "SignalBoard"}],
                    }
                ],
            }
        )
    )
    return profile, cases


def _response(request: httpx.Request) -> httpx.Response:
    assert request.url.host == "fixture.invalid"
    payload = json.loads(request.content)
    assert payload["response_format"]["type"] == "json_schema"
    output = {
        "entities": [
            {"name": "Mira", "type": "person"},
            {"name": "SignalBoard", "type": "system"},
        ],
        "relations": [
            {
                "head": "Mira",
                "relation": "owns",
                "tail": "SignalBoard",
                "evidence": "Mira owns SignalBoard.",
            }
        ],
    }
    return httpx.Response(
        200,
        json={
            "choices": [
                {
                    "message": {"role": "assistant", "content": json.dumps(output)},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 40, "completion_tokens": 20},
        },
    )


def test_external_cases_real_factory_transport_and_metered_usage(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use injected HTTP and synthetic keys while retaining normal parsing and durable traces."""
    profile, cases = _inputs(tmp_path)

    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        pytest.fail("Mock evaluation attempted a real network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)

    def extraction_key(_name: str | None) -> SecretStr:
        return SecretStr("synthetic-fixture-key")

    settings = SimpleNamespace(extraction_key=extraction_key, provider_timeout=10)
    monkeypatch.setattr(factory, "get_settings", lambda: settings)
    original = factory.create_extractor
    with httpx.Client(transport=httpx.MockTransport(_response), trust_env=False) as client:

        def injected(item: ExtractionProfile) -> AbstractContextManager[ExtractorAdapter]:
            return original(item, client=client)

        monkeypatch.setattr(factory, "create_extractor", injected)
        report = evaluate(db, str(profile), cases)
    traces = list_traces(db, report.id)
    assert len(traces) > 1
    assert all(trace.call_type == "extraction" for trace in traces)
    assert all(trace.billing_status == "unknown" for trace in traces)
    assert report.input_tokens == len(traces) * 40
    assert report.output_tokens == len(traces) * 20
    assert report.cost_usd is None
    assert report.product.all.relation_strict.f1 == 1
    assert report.product.verified.relation_strict.f1 == 1
