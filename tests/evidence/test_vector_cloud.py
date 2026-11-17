# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline MockTransport tests for governed real-mode cloud vector encoding."""

from __future__ import annotations

import hashlib
import json
import socket
from http import HTTPStatus
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from datakeel.core.data_asset_models import AccessContext
from datakeel.core.vector_models import EmbedParams, VectorError, VectorPolicy
from datakeel.core.vector_query import VectorKind, VectorQuery
from datakeel.evidence.vector_cloud import (
    CloudVectorTransport,
    _verify_destination,
    use_cloud_vector_transport,
)
from datakeel.pipeline.models import Node, Pipeline
from datakeel.storage.evidence_projection import projection_hash, rebuild_evidence
from datakeel.storage.evidence_store import list_assertions
from datakeel.storage.vector_budget import list_vector_attempts
from datakeel.storage.vector_cache import vector_cached
from datakeel.storage.vector_queries import query_vectors
from datakeel.storage.vector_rows import VectorAccountRow, VectorCacheRow
from tests.evidence.vector_helpers import vector_dataset, vector_prepare, vector_run

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _real_embed_params(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "mode": "real",
        "fake_version": "we-cloud-http-v1",
        "endpoint": "https://api.openai.com/v1/embeddings",
        "modality": "text",
        "dimensions": 64,
        "tokenizer": "utf8-byte-bound-v1",
        "model": "text-embedding-3-small",
        "credential_env": "DATAKEEL_EMBEDDING_API_KEY",
        "policy": {
            "currency": "CNY",
            "price_version": "cloud-price-v1",
            "nanos_per_token": 100,
            "image_tokens": 100,
            "max_requests": 50,
            "max_cost_nanos": 10_000_000,
            "real_budget_cny": 0.01,
            "real_egress_enabled": True,
        },
    }
    base.update(overrides)
    return base


def _five_node_real_pipeline(reference_dataset_id: str) -> Pipeline:
    return Pipeline(
        nodes=[
            Node(
                id="embed",
                operator="evidence.vector_embed",
                inputs={"files": "$input.files"},
                params=_real_embed_params(),
            ),
            Node(
                id="dup",
                operator="evidence.semantic_duplicate",
                inputs={"files": "embed.files"},
                params={"threshold": 0.95},
            ),
            Node(
                id="cluster",
                operator="evidence.semantic_cluster",
                inputs={"files": "embed.files"},
                params={"eps": 0.05, "min_samples": 2},
            ),
            Node(
                id="outlier",
                operator="evidence.semantic_outlier",
                inputs={"files": "embed.files"},
                params={"eps": 0.05, "min_samples": 2},
            ),
            Node(
                id="gap",
                operator="evidence.coverage_gap",
                inputs={"files": "embed.files"},
                params={"reference": {"dataset_id": reference_dataset_id}, "threshold": 0.99},
            ),
        ],
        outputs=["dup.files", "cluster.files", "outlier.files", "gap.files"],
        max_workers=1,
    )


def _deterministic_vector(body: bytes, dimensions: int = 64) -> list[float]:
    digest = hashlib.sha256(body).digest()
    return [float(digest[index % len(digest)] + 1) for index in range(dimensions)]


@pytest.mark.parametrize(
    ("override", "expected_fragment"),
    [
        ({"endpoint": "https://embedding.example.invalid/v1/embeddings"}, "real_endpoint_invalid"),
        ({"endpoint": "http://api.openai.com/v1/embeddings"}, "real_endpoint_invalid"),
        ({"endpoint": "https://192.0.2.1/v1/embeddings"}, "real_endpoint_invalid"),
        ({"endpoint": "https://api.openai.com/v1/embeddings?x=1"}, "real_endpoint_invalid"),
        ({"credential_env": None}, "real_endpoint_requires_credential_env"),
        ({"fake_version": "we-e2-fake-v1"}, "real_embedding_profile_invalid"),
        ({"tokenizer": "fake-codepoint-v1"}, "real_embedding_profile_invalid"),
        ({"model": None}, "real_embedding_profile_invalid"),
        ({"model": "multimodal-embedding-v1"}, "real_embedding_profile_invalid"),
    ],
)
def test_real_embed_params_reject_unsafe_or_incomplete_profiles(
    override: dict[str, object], expected_fragment: str
) -> None:
    """Real cloud mode refuses reserved/non-TLS/non-global URLs and incomplete profiles."""
    with pytest.raises(ValidationError, match=expected_fragment):
        EmbedParams.model_validate(_real_embed_params(**override))


def test_embed_params_accept_loopback_and_guard_fake_and_budget_contracts() -> None:
    """Loopback allows keyless HTTP while fake mode and CNY nano-budgets stay strictly checked."""
    bare_fake = EmbedParams()
    assert bare_fake.effective_model() == "text-embedding-v4"
    assert "model" not in bare_fake.model_dump(mode="json")
    assert "credential_env" not in bare_fake.model_dump(mode="json")
    with pytest.raises(ValidationError):
        EmbedParams.model_validate({"mode": "real"})
    with pytest.raises(ValidationError, match="fake_mode_forbids_real_settings"):
        EmbedParams.model_validate({"credential_env": "DATAKEEL_EMBEDDING_API_KEY"})
    with pytest.raises(ValidationError, match="real_budget_policy_invalid"):
        EmbedParams.model_validate(
            _real_embed_params(
                policy=VectorPolicy(
                    price_version="cloud-price-v1",
                    real_budget_cny=0.02,
                    max_cost_nanos=10_000_000,
                    real_egress_enabled=True,
                ).model_dump()
            )
        )
    loopback = EmbedParams.model_validate(
        _real_embed_params(
            endpoint="http://127.0.0.1:11434/v1/embeddings",
            credential_env=None,
            model="text-embedding-v4",
        )
    )
    assert loopback.effective_model() == "text-embedding-v4"


def _mock_cloud_handler(calls: list[httpx.Request], request: httpx.Request) -> httpx.Response:
    calls.append(request)
    assert request.headers.get("authorization") == "Bearer fixture-embedding-key"
    payload = json.loads(request.content.decode())
    assert payload["model"] == "text-embedding-3-small"
    assert payload["dimensions"] == 64
    used = max(1, len(payload["input"][0].encode()) // 2)
    return httpx.Response(
        HTTPStatus.OK,
        headers={"x-request-id": f"req_{len(calls)}"},
        json={
            "object": "list",
            "model": "text-embedding-3-small",
            "data": [
                {
                    "object": "embedding",
                    "index": 0,
                    "embedding": _deterministic_vector(request.content),
                }
            ],
            "usage": {"prompt_tokens": used, "total_tokens": used},
        },
    )


def _assert_real_queries(db: Database, run_id: str) -> None:
    access = AccessContext(actor="local", entry="ask", scope="query")
    kinds: tuple[VectorKind, ...] = ("duplicate", "cluster", "outlier", "coverage")
    for kind in kinds:
        queried = query_vectors(db, VectorQuery(run_id=run_id, kind=kind), access)
        assert queried.status == "current"
        assert queried.report.mode == "real"
        assert all(ev.mode == "real" for ev in queried.events)
        assert all(ev.implementation == "we-cloud-http-v1" for ev in queried.events)


def test_real_five_node_dag_cold_hot_cache_isolation_and_offline_rebuild(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cold real DAG settles exact provider usage; hot replay and rebuild use zero HTTP calls."""
    monkeypatch.setenv("DATAKEEL_EMBEDDING_API_KEY", "fixture-embedding-key")
    target = vector_dataset(db, tmp_path / "target", (b"dup-item", b"dup-item", b"singleton-gap"))
    reference = vector_dataset(db, tmp_path / "ref", (b"reference-anchor",))
    calls: list[httpx.Request] = []
    pipeline = _five_node_real_pipeline(reference)
    transport = httpx.MockTransport(lambda req: _mock_cloud_handler(calls, req))
    with use_cloud_vector_transport(transport):
        cold = vector_run(db, target, pipeline)
        assert cold.state == "COMPLETED", cold.error
        assert len(calls) == 4
        assert cold.vector is not None
        assert cold.vector.mode == "real"
        embed_report = cold.vector.nodes[0]
        assert embed_report.real_requests == 4
        assert embed_report.real_usage is not None
        assert embed_report.real_cost_nanos == embed_report.real_usage * 100
        assert embed_report.fake_requests == 0
        assert all(attempt.state == "SETTLED" for attempt in cold.vector.attempts)
        assert {a.response_id for a in cold.vector.attempts} == {"req_1", "req_2", "req_3", "req_4"}
        hot = vector_run(db, target, pipeline)
        assert hot.state == "COMPLETED", hot.error
        assert len(calls) == 4
        assert hot.vector is not None
        assert hot.vector.attempts == ()
        assert hot.vector.nodes[0].cache_hits == 4

    _assert_real_queries(db, hot.id)
    fake_run = vector_run(db, target)
    assert fake_run.vector is not None
    assert fake_run.vector.mode == "fake"
    assert len(fake_run.vector.attempts) == 3

    expected_hash = projection_hash(db)
    monkeypatch.setattr(
        CloudVectorTransport,
        "send",
        lambda *_a, **_k: pytest.fail("rebuild invoked cloud transport"),
    )
    rebuilt = rebuild_evidence(db)
    assert rebuilt.matches
    assert rebuilt.after_hash == expected_hash


def test_missing_credentials_fail_before_sending_and_refund_on_fencing(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing env credentials fail before SENDING so task fencing refunds the reservation."""
    monkeypatch.delenv("DATAKEEL_EMBEDDING_API_KEY", raising=False)
    dataset = vector_dataset(db, tmp_path / "inputs", (b"alpha", b"beta"))
    pipeline = Pipeline(
        nodes=[
            Node(
                id="embed",
                operator="evidence.vector_embed",
                inputs={"files": "$input.files"},
                params=_real_embed_params(),
            )
        ],
        outputs=["embed.files"],
        max_workers=1,
    )
    plan = vector_prepare(db, dataset, pipeline)
    failed = vector_run(db, dataset, pipeline)
    assert failed.state == "FAILED"
    assert failed.vector is not None
    assert failed.vector.mode == "real"
    assert failed.vector.reason == "vector_missing_credentials"
    attempts = list_vector_attempts(db, failed.id)
    assert len(attempts) == 1
    assert attempts[0].state == "REFUNDED"
    with db.session() as session:
        account = session.get(VectorAccountRow, plan.id)
        if account is not None:
            # Fencing refunds unsent RESERVED occupancy back to zero.
            assert account.requests >= 0


def test_destination_dns_ssrf_guard_blocks_non_global_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS answers resolving to loopback, link-local or documentation ranges are refused."""
    _verify_destination("http://localhost:11434/v1/embeddings", custom_transport=False)
    _verify_destination("https://api.openai.com/v1/embeddings", custom_transport=True)

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))],
    )
    with pytest.raises(VectorError, match="vector_unsafe_destination"):
        _verify_destination("https://api.openai.com/v1/embeddings", custom_transport=False)

    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [])
    with pytest.raises(VectorError, match="vector_provider_unreachable"):
        _verify_destination("https://api.openai.com/v1/embeddings", custom_transport=False)

    def broken_dns(*_args: object, **_kwargs: object) -> list[object]:
        raise socket.gaierror

    monkeypatch.setattr(socket, "getaddrinfo", broken_dns)
    with pytest.raises(VectorError, match="vector_provider_unreachable"):
        _verify_destination("https://api.openai.com/v1/embeddings", custom_transport=False)

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    _verify_destination("https://api.openai.com/v1/embeddings", custom_transport=False)


@pytest.mark.parametrize(
    ("kind", "expected_reason"),
    [
        ("redirect", "vector_redirect_refused"),
        ("auth", "vector_authentication_failed"),
        ("server_error", "vector_protocol_failure"),
        ("bad_json", "vector_invalid_response"),
        ("wrong_dims", "vector_response_mapping_invalid"),
        ("timeout", "vector_provider_timeout"),
        ("connect_error", "vector_provider_unreachable"),
    ],
)
def test_dispatched_cloud_failures_retain_unknown_occupancy_and_publish_nothing(
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    expected_reason: str,
) -> None:
    """Once SENDING is committed, uncertain or invalid provider replies retain UNKNOWN budget."""
    monkeypatch.setenv("DATAKEEL_EMBEDDING_API_KEY", "fixture-embedding-key")
    dataset = vector_dataset(db, tmp_path / kind, (b"payload-one",))
    pipeline = Pipeline(
        nodes=[
            Node(
                id="embed",
                operator="evidence.vector_embed",
                inputs={"files": "$input.files"},
                params=_real_embed_params(),
            )
        ],
        outputs=["embed.files"],
        max_workers=1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "redirect":
            return httpx.Response(HTTPStatus.FOUND, headers={"location": "https://example.com"})
        if kind == "auth":
            return httpx.Response(HTTPStatus.UNAUTHORIZED, json={"error": "bad key"})
        if kind == "server_error":
            return httpx.Response(HTTPStatus.BAD_GATEWAY, text="upstream error")
        if kind == "bad_json":
            return httpx.Response(HTTPStatus.OK, content=b"{not-json")
        if kind == "wrong_dims":
            return httpx.Response(
                HTTPStatus.OK,
                json={
                    "id": "bad_dim",
                    "object": "list",
                    "model": "text-embedding-3-small",
                    "data": [{"object": "embedding", "index": 0, "embedding": [1.0, 2.0]}],
                    "usage": {"total_tokens": 3},
                },
            )
        msg = "failure"
        if kind == "timeout":
            raise httpx.ReadTimeout(msg, request=request)
        raise httpx.ConnectError(msg, request=request)

    with use_cloud_vector_transport(httpx.MockTransport(handler)):
        result = vector_run(db, dataset, pipeline)
    assert result.state == "FAILED"
    assert result.vector is not None
    assert result.vector.reason == expected_reason
    attempts = list_vector_attempts(db, result.id)
    assert len(attempts) == 1
    assert attempts[0].state == "UNKNOWN"
    assert attempts[0].reason == expected_reason
    assert list_assertions(db) == []


def _throttled_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    if payload["input"] == ["throttled-item"]:
        return httpx.Response(HTTPStatus.TOO_MANY_REQUESTS, json={"error": "rate limit"})
    return httpx.Response(
        HTTPStatus.OK,
        headers={"x-request-id": "bad header with spaces!"},
        json={
            "object": "list",
            "model": "text-embedding-3-small",
            "data": [
                {
                    "object": "embedding",
                    "index": 0,
                    "embedding": _deterministic_vector(request.content),
                }
            ],
            "usage": {"total_tokens": 2},
        },
    )


def test_rate_limit_temporary_failure_yields_partial_success_without_caching_failed_item(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP 429 marks one input temporary_input_failure while keeping valid peer duplicates."""
    monkeypatch.setenv("DATAKEEL_EMBEDDING_API_KEY", "fixture-embedding-key")
    dataset = vector_dataset(db, tmp_path / "partial", (b"twin", b"twin", b"throttled-item"))
    pipeline = Pipeline(
        nodes=[
            Node(
                id="embed",
                operator="evidence.vector_embed",
                inputs={"files": "$input.files"},
                params=_real_embed_params(),
            ),
            Node(
                id="dup",
                operator="evidence.semantic_duplicate",
                inputs={"files": "embed.files"},
                params={"threshold": 0.99},
            ),
        ],
        outputs=["dup.files"],
        max_workers=1,
    )
    with use_cloud_vector_transport(httpx.MockTransport(_throttled_handler)):
        result = vector_run(db, dataset, pipeline)
    assert result.state == "COMPLETED", result.error
    assert result.partial
    assert result.vector is not None
    assert result.vector.status == "partial_success"
    assert len(list_assertions(db)) == 1
    states = sorted(attempt.state for attempt in result.vector.attempts)
    assert states == ["SETTLED", "SETTLED", "UNKNOWN"]
    with db.session() as session:
        cached_count = session.scalar(select(func.count()).select_from(VectorCacheRow))
        assert cached_count == 1
        row = session.scalars(select(VectorCacheRow)).first()
        assert row is not None
        key = str(row.payload["key"])
    assert (
        vector_cached(db, key, "embedding", mode="real", implementation="we-cloud-http-v1")
        is not None
    )
    assert vector_cached(db, key, "embedding") is None
    kind: VectorKind = "duplicate"
    queried = query_vectors(
        db,
        VectorQuery(run_id=result.id, kind=kind),
        AccessContext(actor="local", entry="ask", scope="query"),
    )
    assert queried.total == 1
    assert queried.report.status == "partial_success"


def test_loopback_keyless_real_mode_omits_authorization_header(
    db: Database, tmp_path: Path
) -> None:
    """Loopback real mode sends no Authorization header when credential_env is omitted."""
    dataset = vector_dataset(db, tmp_path / "loopback", (b"local-ollama-item",))
    pipeline = Pipeline(
        nodes=[
            Node(
                id="embed",
                operator="evidence.vector_embed",
                inputs={"files": "$input.files"},
                params=_real_embed_params(
                    endpoint="http://127.0.0.1:11434/v1/embeddings",
                    credential_env=None,
                    model="text-embedding-v4",
                ),
            )
        ],
        outputs=["embed.files"],
        max_workers=1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(
            HTTPStatus.OK,
            json={
                "id": "ollama_embed_1",
                "object": "list",
                "model": "text-embedding-v4",
                "data": [
                    {
                        "object": "embedding",
                        "index": 0,
                        "embedding": _deterministic_vector(request.content),
                    }
                ],
                "usage": {"total_tokens": 1},
            },
        )

    with use_cloud_vector_transport(httpx.MockTransport(handler)):
        done = vector_run(db, dataset, pipeline)
    assert done.state == "COMPLETED", done.error
    assert done.vector is not None
    assert done.vector.attempts[0].response_id == "ollama_embed_1"
