# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Portable metadata strips common credential forms without losing public source links."""

import pytest

from datakeel.core.models import JsonDocument
from datakeel.core.portable_metadata import portable_metadata
from datakeel.core.release_models import annotation_statistics


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
        "  File:///private/example  ",
    ],
)
def test_storage_uris_are_omitted_regardless_of_case_or_whitespace(value: str) -> None:
    """An explicit storage URI scheme declares a location in any field or collection."""
    assert portable_metadata({"reference": value, "nested": [value, "public"]}) == {
        "nested": ["public"]
    }


@pytest.mark.parametrize(
    "value",
    [
        r"\\generated-host\share\example",
        "~/generated/example",
        "  /private/example  ",
        "C:\\private\\example",
    ],
)
def test_bare_paths_are_omitted_only_from_declared_location_fields(value: str) -> None:
    """A path-like string is private by its field's role, never by its first character."""
    document = JsonDocument(
        {"local_path": value, "nested": {"image_path": value, "note": value}}
    ).root
    assert portable_metadata(document) == {"nested": {"note": value}}


def test_slash_prefixed_labels_survive_with_their_counts() -> None:
    """Real vocabulary identifiers such as /m/01yrx stay in deliveries and statistics."""
    metadata = JsonDocument(
        {
            "labels": ["/m/01yrx", "/m/0bt9lr", "cat"],
            "annotations": [{"bbox": [1, 2, 3, 4], "label": "/m/01yrx"}],
            "unit": "/s",
            "endpoint": "/v1/items",
            "source_path": "/private/example",
        }
    ).root
    result = portable_metadata(metadata)
    assert result == {key: value for key, value in metadata.items() if key != "source_path"}
    assert annotation_statistics(result) == (1, 3)
