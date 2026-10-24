# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Configuration uses the declared prefix and fresh environment snapshots."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from datakeel.core.settings import Settings, get_settings


def test_settings_when_prefixed_environment_set_parse_path_and_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify settings when prefixed environment set parse path and timeout."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path))
    monkeypatch.setenv("DATAKEEL_REPORT_TIMEOUT", "4.5")
    assert (get_settings().home, get_settings().report_timeout) == (tmp_path, 4.5)


def test_settings_when_unprefixed_variable_set_ignore_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify settings when unprefixed variable set ignore it."""
    monkeypatch.delenv("DATAKEEL_S3_BUCKET", raising=False)
    monkeypatch.setenv("S3_BUCKET", "unrelated")
    assert get_settings().s3_bucket is None


def test_settings_when_environment_changes_resolve_fresh_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify settings when environment changes resolve fresh values."""
    monkeypatch.setenv("DATAKEEL_HOME", "first")
    first = get_settings()
    monkeypatch.setenv("DATAKEEL_HOME", "second")
    assert (first.home, get_settings().home) == (Path("first"), Path("second"))


def test_settings_when_environment_unchanged_reuse_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify settings when environment unchanged reuse instance."""
    monkeypatch.setenv("DATAKEEL_HOME", "shared")
    assert get_settings() is get_settings()


@pytest.mark.parametrize("timeout", [0, -1, 31])
def test_settings_when_timeout_outside_bounds_rejects_input(timeout: int) -> None:
    """Verify settings when timeout outside bounds rejects input."""
    with pytest.raises(ValidationError, match="report_timeout"):
        Settings(report_timeout=timeout)


def test_settings_when_unknown_field_provided_rejects_input() -> None:
    """Verify settings when unknown field provided rejects input."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Settings.model_validate({"unknown_option": "value"})


def test_settings_when_reassigned_rejects_mutation() -> None:
    """Verify settings when reassigned rejects mutation."""
    settings = Settings()
    with pytest.raises(ValidationError, match="frozen_instance"):
        settings.report_timeout = 20


def test_extraction_key_is_explicit_and_not_part_of_serialized_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the requested variable is resolved, and its value stays a SecretStr."""
    monkeypatch.setenv("KG_TEST_KEY", "synthetic-credential")
    settings = Settings()
    key = settings.extraction_key("KG_TEST_KEY")
    assert key is not None
    assert key.get_secret_value() == "synthetic-credential"
    assert settings.extraction_key(None) is None
    assert settings.extraction_key("KG_UNSET_TEST_KEY") is None
    assert "synthetic-credential" not in settings.model_dump_json()
