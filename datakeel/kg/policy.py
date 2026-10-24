# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Classify external model transfer using literal hosts without DNS lookups."""

from ipaddress import IPv4Address, ip_address
from urllib.parse import urlsplit

from datakeel.core.kg_contracts import ExtractionProfile


def target_host(profile: ExtractionProfile) -> str | None:
    """Return the configured destination or the provider's known default host."""
    if profile.base_url:
        return urlsplit(profile.base_url).hostname
    return {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}.get(profile.provider)


def is_external(profile: ExtractionProfile) -> bool:
    """Allow only offline providers and explicitly enumerated loopback host literals."""
    if profile.provider in {"fake", "replay", "gliner2"}:
        return False
    host = target_host(profile)
    if host is None:
        return True
    if host.lower() in {"localhost", "localhost."}:
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return True
    return not ((isinstance(address, IPv4Address) and address.is_loopback) or str(address) == "::1")
