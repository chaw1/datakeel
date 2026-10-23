# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit request-scoped infrastructure dependencies."""

from typing import Annotated, cast

from fastapi import Depends, Request

from datakeel.storage.database import Database


def get_database(request: Request) -> Database:
    """Resolve the database owned by the current application."""
    return cast("Database", request.app.state.db)


DatabaseDependency = Annotated[Database, Depends(get_database)]
