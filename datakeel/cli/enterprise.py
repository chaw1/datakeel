# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Seed the fictional enterprise through controlled imports and preserve user semantics."""

from datakeel.actions import service as actions
from datakeel.actions.catalog_parameters import ImportCatalogParams
from datakeel.actions.models import ExecuteRequest
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskAnswer, AskRequest
from datakeel.core.catalog_models import CatalogImportRequest, CatalogQuery
from datakeel.core.errors import ExecutionError
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.harness.resources import contract_path
from datakeel.metrics.loader import load_layer
from datakeel.sample_enterprise import generate_enterprise
from datakeel.sample_enterprise.models import SourceSample
from datakeel.storage.catalog_queries import read_objects
from datakeel.storage.database import Database, data_dir
from datakeel.storage.metric_store import install_layer, list_metrics

PRIMARY_QUESTION = "上个季度华东区零售额是多少"


class EnterpriseImport(BoundaryModel):
    """Summarize the controlled plan, run, and import statistics for one synthetic source."""

    source_id: str
    plan_id: str
    run_id: str
    details: JsonDocument


class EnterpriseDemo(BoundaryModel):
    """Expose the generated scenario, observable imports, and a replayable primary answer."""

    company: str = "Fictional Kitchen Co."
    sources: tuple[SourceSample, ...]
    imports: tuple[EnterpriseImport, ...]
    table_count: int
    column_count: int
    metric_count: int
    answer: AskAnswer


def _import_source(db: Database, source: SourceSample) -> EnterpriseImport:
    params = ImportCatalogParams(
        request=CatalogImportRequest(
            source_id=source.id, name=source.name, connection_url=f"sqlite:///{source.path}"
        )
    )
    plan = actions.prepare_action(
        db,
        "import_catalog",
        JsonDocument.model_validate(
            params.model_dump(mode="json", exclude={"snapshot", "parse_failures"})
        ),
    )
    run = actions.execute_plan(
        db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, operation_id=plan.operation_id)
    )
    if run.status != "SUCCEEDED" or run.receipt is None:
        msg = run.error or "Enterprise catalog import did not succeed"
        raise ExecutionError(msg)
    return EnterpriseImport(
        source_id=source.id,
        plan_id=plan.id,
        run_id=run.id,
        details=JsonDocument.model_validate(run.receipt.quality["details"]),
    )


def seed_enterprise_demo(db: Database) -> EnterpriseDemo:
    """Import deterministic sources, install only an absent semantic layer, and ask once."""
    sample = generate_enterprise(data_dir() / "enterprise")
    imports = tuple(_import_source(db, source) for source in sample.sources)
    if not list_metrics(db):
        install_layer(db, load_layer(contract_path("semantic-layer")))
    answer = ask_data(
        db, AskRequest(question=PRIMARY_QUESTION, reference_instant=sample.reference_instant)
    )
    return EnterpriseDemo(
        sources=sample.sources,
        imports=imports,
        answer=answer,
        table_count=read_objects(db, CatalogQuery(kind="table", limit=1)).total,
        column_count=read_objects(db, CatalogQuery(kind="column", limit=1)).total,
        metric_count=len(list_metrics(db)),
    )
