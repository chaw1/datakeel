# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Classify image transfer without DNS resolution or contacting any endpoint."""

from ipaddress import IPv4Address, ip_address
from urllib.parse import urlsplit

from datakeel.core.transcription_models import TranscriptionProfile


def target_host(profile: TranscriptionProfile) -> str | None:
    """Expose the exact destination host for the frozen consent card."""
    return urlsplit(profile.base_url).hostname if profile.base_url else None


def is_external(profile: TranscriptionProfile) -> bool:
    """Treat every non-loopback VLM endpoint as external, including private networks."""
    if profile.backend != "vlm":
        return False
    host = target_host(profile)
    if host and host.lower() in {"localhost", "localhost."}:
        return False
    try:
        address = ip_address(host or "")
    except ValueError:
        return True
    return not ((isinstance(address, IPv4Address) and address.is_loopback) or str(address) == "::1")
