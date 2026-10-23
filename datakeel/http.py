# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""HTTP clients use explicit transport configuration and never ambient proxies."""

import httpx


class Client(httpx.Client):
    """Provide a small synchronous JSON client for local verification commands."""

    def __init__(self, base_url: str = "", timeout: float = 10) -> None:
        """Use only the provided HTTP target and a finite timeout."""
        super().__init__(base_url=base_url, timeout=timeout, trust_env=False)


Response = httpx.Response
