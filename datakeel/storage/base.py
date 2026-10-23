# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One metadata registry for all authoritative persistence models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Share one declarative metadata collection without engine dependencies."""
