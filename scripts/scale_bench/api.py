# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise a bounded HTTP workload through FastAPI's real ASGI request boundary."""

import asyncio
from array import array
from collections import Counter
from http import HTTPStatus
from math import ceil
from time import perf_counter

import httpx
from pydantic import TypeAdapter, ValidationError

from datakeel.api.app import create_app
from datakeel.core.ask_models import AskAnswer
from datakeel.core.search_models import SearchResult
from datakeel.storage.views import DatasetView, FileView
from scripts.scale_bench.common import check_resources, fingerprint
from scripts.scale_bench.datasets import seed_dataset
from scripts.scale_bench.metrics import MetricFixture, prepare, request, valid_answer
from scripts.scale_bench.models import Context, Latency, ScenarioResult

_HISTOGRAM_LIMIT_MS = 60_000
_FILE_LIMIT = 50
_SEARCH_LIMIT = 20
_ROUTES = ("list", "search", "object", "ask")
_FILE_PAGE = TypeAdapter(list[FileView])
_SEARCH_PAGE = TypeAdapter(list[SearchResult])


class Histogram:
    """Retain fixed one-millisecond counters; mutable only inside one workload loop."""

    def __init__(self) -> None:
        """Allocate at most 60,001 counters regardless of completed request count."""
        self.buckets = array("Q", [0]) * (_HISTOGRAM_LIMIT_MS + 1)
        self.count = 0
        self.errors = 0
        self.max_ms = 0.0
        self.overflow = 0

    def add(self, milliseconds: float, *, error: bool = False) -> None:
        """Record one request and account for durations beyond the bounded histogram."""
        bucket = ceil(milliseconds)
        self.buckets[min(bucket, _HISTOGRAM_LIMIT_MS)] += 1
        self.count += 1
        self.errors += int(error)
        self.max_ms = max(self.max_ms, milliseconds)
        self.overflow += int(bucket > _HISTOGRAM_LIMIT_MS)

    def summary(self) -> Latency:
        """Report nearest-rank upper bounds with at most one millisecond rounding."""
        ranks = [ceil(self.count * quantile / 100) for quantile in (50, 95, 99)]
        values: list[float] = []
        cumulative = 0
        for milliseconds, count in enumerate(self.buckets):
            cumulative += count
            while len(values) < len(ranks) and cumulative >= ranks[len(values)]:
                values.append(
                    self.max_ms
                    if milliseconds == _HISTOGRAM_LIMIT_MS and self.overflow
                    else float(milliseconds)
                )
        return Latency(
            count=self.count,
            errors=self.errors,
            p50_ms=values[0],
            p95_ms=values[1],
            p99_ms=values[2],
            max_ms=self.max_ms,
        )


async def _request(
    client: httpx.AsyncClient, context: Context, dataset_id: str, fixture: MetricFixture, index: int
) -> tuple[str, str | None]:
    route = _ROUTES[index % len(_ROUTES)]
    if route == "ask":
        query_index = index // len(_ROUTES)
        response = await client.post("/api/ask", json=request(query_index).model_dump(mode="json"))
        if response.status_code != HTTPStatus.OK:
            return route, f"http_{response.status_code}"
        answer = AskAnswer.model_validate_json(response.content)
        error = None if valid_answer(answer, fixture, query_index) else f"answer_{answer.status}"
        return route, error
    paths = {
        "list": f"/api/datasets/{dataset_id}/files?limit={_FILE_LIMIT}",
        "search": f"/api/search?q=file&limit={_SEARCH_LIMIT}",
        "object": f"/api/datasets/{dataset_id}",
    }
    response = await client.get(paths[route])
    if response.status_code != HTTPStatus.OK:
        return route, f"http_{response.status_code}"
    if route == "list":
        files = _FILE_PAGE.validate_json(response.content)
        expected_ids = [
            f"file-{context.config.seed}-{number:09d}"
            for number in range(min(_FILE_LIMIT, context.scale.files))
        ]
        return route, None if [item.id for item in files] == expected_ids else "page_oracle"
    if route == "search":
        results = _SEARCH_PAGE.validate_json(response.content)
        valid = len(results) == min(_SEARCH_LIMIT, context.scale.files) and all(
            item.kind == "file" and "file" in item.name.casefold() for item in results
        )
        return route, None if valid else "search_oracle"
    dataset = DatasetView.model_validate_json(response.content)
    valid = (dataset.id, dataset.file_count) == (dataset_id, context.scale.files)
    return route, None if valid else "object_oracle"


async def _load(
    context: Context, dataset_id: str, fixture: MetricFixture
) -> tuple[dict[str, Histogram], float, Counter[str]]:
    histograms = {key: Histogram() for key in (*_ROUTES, "all")}
    errors: Counter[str] = Counter()
    transport = httpx.ASGITransport(app=create_app(context.db), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://benchmark.test") as client:
        started = perf_counter()
        deadline = started + context.scale.duration_seconds

        async def user(number: int) -> None:
            index = number
            while perf_counter() < deadline:
                before = perf_counter()
                route = _ROUTES[index % len(_ROUTES)]
                try:
                    route, error = await _request(client, context, dataset_id, fixture, index)
                except httpx.HTTPError:
                    error = "transport"
                except ValidationError:
                    error = "invalid_payload"
                if error is not None:
                    errors[f"{route}_{error}"] += 1
                milliseconds = (perf_counter() - before) * 1000
                histograms[route].add(milliseconds, error=error is not None)
                histograms["all"].add(milliseconds, error=error is not None)
                index += 1

        await asyncio.gather(*(user(index) for index in range(context.scale.virtual_users)))
        return histograms, perf_counter() - started, errors


def run(context: Context) -> ScenarioResult:
    """Run closed-loop virtual users against list, search, object, and metric HTTP reads."""
    started = perf_counter()
    dataset_id = seed_dataset(context)
    fixture = prepare(context)
    setup = perf_counter() - started
    histograms, duration, errors = asyncio.run(_load(context, dataset_id, fixture))
    check_resources(context)
    aggregate = histograms["all"]
    return ScenarioResult(
        scenario="B5",
        counts={
            "files": context.scale.files,
            "fact_rows": fixture.rows,
            "virtual_users": context.scale.virtual_users,
            "requests": aggregate.count,
            **{f"error_{kind}": count for kind, count in errors.items()},
        },
        metrics={
            "setup_seconds": setup,
            "requested_seconds": context.scale.duration_seconds,
            "elapsed_seconds": duration,
            "requests_per_second": aggregate.count / duration,
            "error_rate": aggregate.errors / max(1, aggregate.count),
            "histogram_overflow": aggregate.overflow,
        },
        latencies={key: value.summary() for key, value in histograms.items()},
        fixture_sha256=fingerprint(
            {
                "facts": fixture.fixture_sha256,
                "files": context.scale.files,
                "seed": context.config.seed,
            }
        ),
        notes=(
            "Real FastAPI ASGI HTTP routing/validation/serialization; no network socket or proxy.",
            "Closed-loop users, no think time; final in-flight requests drain after deadline.",
            "Four routes alternate: paginated files, global search, dataset object, persisted ask.",
            "Ask source uses the full B4 fact-row count for the selected size and stack.",
            "Fixed 1ms histogram through 60s; overflow quantiles conservatively use actual max.",
            "Bounded counts cover HTTP, schema and oracle failures; payloads are discarded.",
        ),
    )
