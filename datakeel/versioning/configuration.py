# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Capture relocatable non-secret configuration contents without activating integrations."""

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import yaml
from pydantic import JsonValue, SecretStr, TypeAdapter
from pydantic import ValidationError as ModelError

from datakeel.core.errors import ValidationError
from datakeel.core.settings import Settings
from datakeel.routing.models import ModelRoutingConfig


def write_configuration(settings: Settings, root: Path) -> tuple[str, ...]:
    """Keep settings and routing contents, replacing credentials with named references only."""
    excluded = tuple(
        name
        for name in type(settings).model_fields
        if isinstance(getattr(settings, name), SecretStr) or name.endswith("username")
    )
    values = TypeAdapter(dict[str, JsonValue]).validate_python(
        settings.model_dump(mode="json", exclude=set(excluded))
    )
    references = list(excluded)
    for name, value in values.items():
        if isinstance(value, str) and any(word in name for word in ("url", "endpoint", "host")):
            parsed = urlsplit(value)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                references.append(name + ".credentials")
                values[name] = urlunsplit(
                    (parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", "")
                )
    values["home"] = "."
    values["database_url"] = "sqlite:///datakeel.db"
    routing: JsonValue = None
    if settings.model_routing_file is not None:
        model = _routing(settings.model_routing_file)
        routing = TypeAdapter(JsonValue).validate_python(model.model_dump(mode="json"))
        values["model_routing_file"] = None  # Contents are embedded; no stale source path.
    document: dict[str, JsonValue] = {"settings": values, "model_routing": routing}
    (root / "config.json").write_bytes(
        TypeAdapter(dict[str, JsonValue]).dump_json(document, indent=2)
    )
    return tuple(sorted(references))


def _routing(path: Path) -> ModelRoutingConfig:
    try:
        return ModelRoutingConfig.model_validate(yaml.safe_load(path.read_text()))
    except (yaml.YAMLError, ModelError) as error:
        msg = "Invalid non-secret routing configuration"
        raise ValidationError(msg) from error
