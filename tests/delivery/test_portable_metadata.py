# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable metadata strips common credential forms without losing public source links."""

import pytest

from datakeel.core.models import JsonDocument
from datakeel.core.portable_metadata import portable_metadata


@pytest.mark.parametrize(
    "value",
    [
        "https://reader:example-password@example.invalid/data",
        "https://reader@example.invalid/data",
        "https://example.invalid/data?X-Amz-Credential=example&X-Amz-Signature=example",
        "https://example.invalid/data?api_key=example",
        "https://example.invalid/data?apiKey=example",
        "https://example.invalid/data?apikey=example",
        "https://example.invalid/data?APIKEY=example",
        "https://example.invalid/data?api.key=example",
        "https:example.invalid/data?ApI_KeY=example",
        "https://example.invalid/data?awssecretaccesskey=example",
        "https://example.invalid/data#clientsecret=example",
        "https://example.invalid/data?sig=example",
        "https://example.invalid/data?KeY=example",
        "https://example.invalid/data?SiG=example",
        "https://example.invalid/data?X-Amz-SiGnAtUrE=example",
        "https://example.invalid/data?X-Amz-CrEdEnTiAl=example",
        "https://example.invalid/data#access_token=example",
        "https://example.invalid/data?access_token=example",
        "https://[invalid/data",
    ],
)
def test_credential_source_urls_are_omitted(value: str) -> None:
    """Authentication embedded in source URLs must never enter a delivery or public release."""
    assert portable_metadata({"source_url": value}) == {}


@pytest.mark.parametrize(
    "key",
    [
        "apiToken",
        "clientSecret",
        "accessKeyId",
        "secretAccessKey",
        "TOKEN",
        "API_KEY",
        "PASSWORD",
        "APIKey",
        "awsSecretAccessKey",
        "apikey",
        "clientsecret",
        "awssecretaccesskey",
        "api.key",
        "api key",
        "storageuri",
        "cReDeNtIaL",
        "pAsSwOrDhAsH",
        "sourcepath",
        "sourceauth",
        "secret",
    ],
)
def test_camelcase_credential_fields_are_omitted(key: str) -> None:
    """Common naming styles cannot bypass recursive credential field filtering."""
    assert portable_metadata({"nested": {key: "example", "label": "public"}}) == {
        "nested": {"label": "public"}
    }


def test_public_source_url_query_and_json_types_are_preserved() -> None:
    """Ordinary citation URLs and numerical metadata remain usable in portable contracts."""
    document = JsonDocument(
        {"source_url": "https://example.invalid/data?page=2", "rating": 1, "reviewed": True}
    ).root
    assert portable_metadata(document) == document


@pytest.mark.parametrize(
    "value",
    [
        "FILE:///private/example",
        "S3://generated-bucket/key",
        "file:/private/example",
        "s3a://generated-bucket/key",
        r"\\generated-host\share\example",
        "~/generated/example",
        "  /private/example  ",
        "  File:///private/example  ",
    ],
)
def test_physical_locations_are_omitted_regardless_of_case_or_whitespace(value: str) -> None:
    """URI spelling and network path forms cannot expose internal storage locations."""
    assert portable_metadata({"reference": value, "nested": [value, "public"]}) == {
        "nested": ["public"]
    }
