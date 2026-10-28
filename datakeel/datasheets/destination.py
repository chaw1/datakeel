# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve the configured paragraph destination without constructing a model client."""

from ipaddress import IPv4Address, ip_address
from urllib.parse import urlsplit

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings


def model_destination(config: ConversationCreate) -> str | None:
    """Expose the exact endpoint for review while rejecting URL-embedded credentials."""
    if config.provider == "fake":
        return None
    settings = get_settings()
    modern = (
        settings.openai_base_url if config.provider == "openai" else settings.anthropic_base_url
    )
    target = modern or (
        settings.openai_url if config.provider == "openai" else settings.anthropic_url
    )
    parsed = urlsplit(target)
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        msg = "Datasheet model endpoint must be an HTTP URL without embedded credentials"
        raise ValidationError(msg)
    return target.rstrip("/")


def is_external_destination(target: str | None) -> bool:
    """Use the same literal-loopback boundary as existing extraction approval policy."""
    if target is None:
        return False
    host = urlsplit(target).hostname
    if host in {"localhost", "localhost."}:
        return False
    try:
        address = ip_address(host or "")
    except ValueError:
        return True
    return not ((isinstance(address, IPv4Address) and address.is_loopback) or str(address) == "::1")
