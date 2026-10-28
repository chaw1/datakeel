# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure deterministic, fully persisted metric answers without a model provider."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from itertools import batched
from pathlib import Path
from threading import Barrier
from time import perf_counter

from sqlalchemy import BigInteger, Column, MetaData, Table, Text, insert, text
from sqlalchemy.engine import Connection

from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot, SourceProperties
from datakeel.core.metric_models import (
    DimensionDefinition,
    Measure,
    MetricDefinition,
    MetricTime,
    SemanticLayer,
)
from datakeel.core.models import AssetRef, JsonDocument
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.metric_store import install_layer
from scripts.scale_bench.common import check_resources, check_space
from scripts.scale_bench.models import BenchModel, Context, Latency, ScenarioResult

_REGIONS = ("华东", "华北", "华南", "西南")
_MULTIPLIER = 1664525
_PERIOD = 10_000


class MetricFixture(BenchModel):
    """Keep independent expected sums alongside the registered metric fixture."""

    rows: int
    expected_total: int
    expected_east: int
    fixture_sha256: str


def _row(index: int, seed: int) -> tuple[int, str, str]:
    return ((index * _MULTIPLIER + seed) % _PERIOD, _REGIONS[index % 4], "2026-07-01")


def prepare(context: Context) -> MetricFixture:
    """Create bounded-batch facts and install a small authoritative semantic layer."""
    rows = context.scale.fact_rows_sqlite if context.db.sqlite else context.scale.fact_rows_pg
    check_resources(context, reserve_bytes=rows * 128)
    schema = "main" if context.db.sqlite else context.schema_name
    if not schema:
        msg = "PostgreSQL metric fixtures require an isolated benchmark schema"
        raise ValueError(msg)
    table = Table(
        "scale_facts",
        MetaData(),
        Column("amount", BigInteger),
        Column("region", Text),
        Column("day", Text),
        schema=schema,
    )
    with context.db.engine.begin() as connection:
        table.create(connection)
        _populate(
            connection, table, rows, context.config.seed, context.root, sqlite=context.db.sqlite
        )
    check_resources(context)
    identity = f"scale/{schema}/scale_facts"
    _register(context, identity)
    period = [_row(index, context.config.seed)[0] for index in range(_PERIOD)]
    full, remaining = divmod(rows, _PERIOD)
    total = full * sum(period) + sum(period[:remaining])
    east = full * sum(period[::4]) + sum(period[:remaining:4])
    return MetricFixture(
        rows=rows,
        expected_total=total,
        expected_east=east,
        fixture_sha256=sha256(f"facts-v1:{context.config.seed}:{rows}".encode()).hexdigest(),
    )


def _populate(
    connection: Connection, table: Table, rows: int, seed: int, root: Path, *, sqlite: bool
) -> None:
    if sqlite:
        for batch in batched(range(rows), 5000):
            check_space(root)
            connection.execute(
                insert(table),
                [
                    dict(zip(("amount", "region", "day"), _row(index, seed), strict=True))
                    for index in batch
                ],
            )
        return
    statement = text(
        "SELECT mod(i * 1664525 + :seed, 10000) AS amount, "
        "(ARRAY['华东','华北','华南','西南'])[mod(i,4)+1] AS region, '2026-07-01' AS day "
        "FROM generate_series(CAST(0 AS BIGINT), :last) AS i"
    ).columns(amount=BigInteger, region=Text, day=Text)
    connection.execute(
        insert(table).from_select(["amount", "region", "day"], statement),
        {"seed": seed % _PERIOD, "last": rows - 1},
    )
    connection.execute(text(f"ANALYZE {table}"))


def _register(context: Context, identity: str) -> None:
    url = context.db.engine.url.render_as_string(hide_password=False)
    source = SourceProperties(connection_url=url, dialect=context.db.engine.dialect.name)
    source_object = CatalogObject(
        asset_ref=AssetRef(asset_type="source", asset_id="scale"),
        name="Scale source",
        properties=JsonDocument(source.model_dump(mode="json")),
    )
    assets = [
        source_object,
        CatalogObject(
            asset_ref=AssetRef(asset_type="table", asset_id=identity),
            name="scale_facts",
            source_id="scale",
            schema_name=identity.split("/")[1],
        ),
    ]
    assets.extend(
        CatalogObject(
            asset_ref=AssetRef(asset_type="column", asset_id=f"{identity}/{name}"),
            name=name,
            source_id="scale",
            table_id=identity,
        )
        for name in ("amount", "region", "day")
    )
    publish_snapshot(context.db, CatalogSnapshot(scope="scale-source", objects=tuple(assets)))
    install_layer(
        context.db,
        SemanticLayer(
            metrics=[
                MetricDefinition(
                    id="scale_sales",
                    name="销售额",
                    description="Synthetic integer sales",
                    owner="Bench",
                    measure=Measure(table=identity, column=f"{identity}/amount", aggregation="sum"),
                    time=MetricTime(column=f"{identity}/day"),
                    dimensions=["scale_region"],
                )
            ],
            dimensions=[
                DimensionDefinition(
                    id="scale_region",
                    name="区域",
                    column=f"{identity}/region",
                    values=list(_REGIONS),
                )
            ],
        ),
    )


def request(index: int = 0) -> AskRequest:
    """Alternate complete and dimension-sliced questions at one fixed reference instant."""
    return AskRequest(
        question="销售额是多少" if index % 2 == 0 else "华东销售额是多少",
        reference_instant=datetime(2026, 10, 1, tzinfo=UTC),
    )


def valid_answer(answer: AskAnswer, fixture: MetricFixture, index: int) -> bool:
    """Check returned numbers against a generator-derived oracle, independent of SQL."""
    expected = fixture.expected_total if index % 2 == 0 else fixture.expected_east
    return (
        answer.status == "answered"
        and answer.result is not None
        and answer.result.rows == [[expected]]
    )


def _measure(context: Context, fixture: MetricFixture, index: int) -> tuple[float, bool]:
    started = perf_counter()
    answer = ask_data(context.db, request(index))
    return (perf_counter() - started) * 1000, not valid_answer(answer, fixture, index)


def summarize(samples: list[tuple[float, bool]]) -> Latency:
    """Summarize a bounded repeated workload with exact nearest-rank quantiles."""
    ordered = sorted(value for value, _error in samples)
    return Latency(
        count=len(samples),
        errors=sum(error for _value, error in samples),
        p50_ms=ordered[max(0, (len(ordered) * 50 + 99) // 100 - 1)],
        p95_ms=ordered[max(0, (len(ordered) * 95 + 99) // 100 - 1)],
        p99_ms=ordered[max(0, (len(ordered) * 99 + 99) // 100 - 1)],
        max_ms=max(ordered),
    )


def run(context: Context) -> ScenarioResult:
    """Time serial and twenty-user metric parsing, execution, and durable evidence."""
    started = perf_counter()
    fixture = prepare(context)
    setup = perf_counter() - started
    serial = [_measure(context, fixture, index) for index in range(context.config.repeats)]

    barrier = Barrier(20)

    def concurrent_measure(index: int) -> tuple[float, bool]:
        barrier.wait(timeout=60)
        return _measure(context, fixture, index)

    with ThreadPoolExecutor(max_workers=20) as pool:
        concurrent = list(pool.map(concurrent_measure, range(20)))
    return ScenarioResult(
        scenario="B4",
        counts={"fact_rows": fixture.rows, "concurrent_users": 20},
        metrics={
            "setup_seconds": setup,
            "expected_total": fixture.expected_total,
            "expected_east": fixture.expected_east,
        },
        latencies={"serial_ask": summarize(serial), "concurrent_ask": summarize(concurrent)},
        fixture_sha256=fixture.fixture_sha256,
        notes=(
            "Full ask_data boundary: parse, resolve, compile, read-only SQL, persist evidence.",
            "No model provider is constructed. Total and region-sliced SUM alternate.",
            "Twenty closed-loop requests start in a thread pool; no client think time.",
        ),
    )
