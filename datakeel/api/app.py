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
    ask,
    catalog,
    datasets,
    evidence,
    governance,
    harness,
    lineage,
    ontology,
    search,
    system,
    tasks,
    workflow_runs,
)
from datakeel.routing.config import load_config
from datakeel.runtime.workflow_service import recover_runs
from datakeel.storage.database import Database


def create_app(db: Database | None = None) -> FastAPI:
    """Create an isolated application with explicit infrastructure dependencies."""
    database = db or Database()
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
        catalog.router,
        ask.router,
        evidence.router,
        tasks.router,
        lineage.router,
        governance.router,
        ontology.router,
        search.router,
        actions.router,
        agent.router,
        harness.router,
        workflow_runs.router,
    ):
        app.include_router(router)
    if system.STATIC_DIRECTORY.is_dir():
        app.mount("/", StaticFiles(directory=system.STATIC_DIRECTORY, html=True), name="web")
    return app
