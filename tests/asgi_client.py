# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""In-process HTTP test client using the application's actual ASGI routes."""

from fastapi.testclient import TestClient

__all__ = ["TestClient"]
