# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Assemble domain routers and the bundled local application."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from datakeel import __version__
from datakeel.api.errors import register_errors
from datakeel.api.routes import (
    actions,
    agent,
    annotation_qa,
    ask,
    catalog,
    custom_operators,
    data_assets,
    datasets,
    datasheets,
    delivery,
    evidence,
    governance,
    harness,
    kg,
    lineage,
    memories,
    metadata_imports,
    ontology,
    openlineage,
    quality_rules,
    releases,
    search,
    standards,
    standards_reporting,
    system,
    tasks,
    training,
    uploads,
    workflow_runs,
)
from datakeel.core.logging import warn_unsafe_subprocess
from datakeel.routing.config import load_config
from datakeel.runtime.workflow_service import recover_runs
from datakeel.storage.database import Database


def create_app(db: Database | None = None) -> FastAPI:
    """Create an isolated application with explicit infrastructure dependencies."""
    database = db or Database()
    warn_unsafe_subprocess()
    database.migrate()
    load_config()
    recover_runs(database)
    app = FastAPI(
        title="Datakeel", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.db = database
    register_errors(app)
    for router in (
        system.router,
        datasets.router,
        training.router,
        delivery.router,
        releases.router,
        uploads.router,
        data_assets.router,
        annotation_qa.router,
        datasheets.router,
        catalog.router,
        custom_operators.router,
        standards.router,
        standards_reporting.router,
        metadata_imports.router,
        openlineage.router,
        ask.router,
        evidence.router,
        kg.router,
        tasks.router,
        lineage.router,
        governance.router,
        ontology.router,
        quality_rules.router,
        search.router,
        actions.router,
        agent.router,
        memories.router,
        harness.router,
        workflow_runs.router,
    ):
        app.include_router(router)
    if system.STATIC_DIRECTORY.is_dir():
        app.mount("/", StaticFiles(directory=system.STATIC_DIRECTORY, html=True), name="web")
    return app
