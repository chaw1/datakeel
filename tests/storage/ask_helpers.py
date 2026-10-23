# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small semantic fixtures for testing question persistence independently of parsing."""

from datetime import UTC, datetime

from datakeel.core.ask_models import AskAnswer, AskRequest, LineageReference, MatchEvidence
from datakeel.core.catalog_models import CatalogObject, CatalogSnapshot
from datakeel.core.metric_models import (
    CompileRequest,
    Measure,
    MetricDefinition,
    MetricTime,
    QueryResult,
    SemanticLayer,
    TermDefinition,
    TermTarget,
)
from datakeel.core.models import AssetRef
from datakeel.metrics.compiler import compile_metric
from datakeel.storage.catalog_store import publish_snapshot
from datakeel.storage.database import Database
from datakeel.storage.metric_store import get_metric, install_layer


def _install(db: Database) -> None:
    table = "sample/main/orders"
    publish_snapshot(
        db,
        CatalogSnapshot(
            scope="source:sample",
            objects=(
                CatalogObject(
                    asset_ref=AssetRef(asset_type="table", asset_id=table), name="orders"
                ),
                *(
                    CatalogObject(
                        asset_ref=AssetRef(asset_type="column", asset_id=f"{table}/{column}"),
                        name=column,
                    )
                    for column in ("amount", "date")
                ),
            ),
        ),
    )
    install_layer(
        db,
        SemanticLayer(
            metrics=[
                MetricDefinition(
                    id="revenue",
                    name="零售额",
                    description="Completed retail revenue",
                    owner="Retail",
                    measure=Measure(table=table, column=f"{table}/amount", aggregation="sum"),
                    time=MetricTime(column=f"{table}/date"),
                    caveats=["Synthetic"],
                )
            ],
            terms=[TermDefinition(term="零售额", means=TermTarget(kind="metric", id="revenue"))],
        ),
    )


def answer_case(db: Database) -> tuple[AskRequest, AskAnswer]:
    """Prepare an actually registered metric, term, and compiler-produced answer."""
    _install(db)
    request = AskRequest(
        question="零售额是多少", reference_instant=datetime(2026, 10, 1, tzinfo=UTC)
    )
    card = get_metric(db, "revenue")
    answer = AskAnswer(
        id="question-one",
        session_id="session-one",
        question=request.question,
        status="answered",
        message="Registered revenue",
        reference_instant=request.reference_instant,
        metric_card=card,
        sql=compile_metric(card, [], CompileRequest()),
        result=QueryResult(columns=["value"], rows=[[30]]),
        matches=(
            MatchEvidence(
                start=0,
                end=3,
                text="零售额",
                source="term:零售额.term",
                match_kind="exact",
                metric_id="revenue",
                term_id="term/零售额",
            ),
        ),
        lineage=LineageReference(asset_id="revenue"),
    )
    return request, answer


def refusal_case() -> tuple[AskRequest, AskAnswer]:
    """Prepare a true unsupported question without any invented metric or value."""
    request = AskRequest(
        question="客户满意度如何", reference_instant=datetime(2026, 10, 1, tzinfo=UTC)
    )
    return request, AskAnswer(
        id="refusal-one",
        session_id="refusal-session",
        question=request.question,
        status="unanswerable",
        message="No registered metric",
        reference_instant=request.reference_instant,
    )
