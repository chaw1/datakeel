# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixture generation cannot inherit a remote database or leave the isolated schema prefix."""

import pytest

from scripts.workbench_fixture import _database


def test_fixture_database_rejects_nonlocal_or_unwrapped_database_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An inherited database URL cannot turn the browser fixture helper into a remote writer."""
    monkeypatch.setenv("DATAKEEL_DATABASE_URL", "postgresql://example.invalid/fixtures")
    with pytest.raises(ValueError, match="authorized local test wrapper"):
        _database("p30_test", use_test_database=False)
    monkeypatch.setenv("DATAKEEL_TEST_DATABASE_URL", "postgresql://example.invalid/fixtures")
    with pytest.raises(ValueError, match="authorized local test wrapper"):
        _database("p30_test", use_test_database=True)
    monkeypatch.setenv("DATAKEEL_TEST_DATABASE_URL", "postgresql://127.0.0.1/fixtures")
    with pytest.raises(ValueError, match="isolated p30_"):
        _database("public", use_test_database=True)


def test_fixture_object_storage_must_remain_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generated browser sources never inherit an external object-storage connection."""
    monkeypatch.setenv("DATAKEEL_S3_BUCKET", "generated-example")
    with pytest.raises(ValueError, match="local object storage"):
        _database("p30_test", use_test_database=False)
