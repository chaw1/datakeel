# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Conditional S3 publication preserves releases under retries, races and stale caches."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from botocore.exceptions import ClientError

from datakeel.core.errors import ConflictError
from datakeel.storage.objects import S3Store, fresh_object
from tests.storage.s3_fixture import ConditionalS3


@pytest.fixture
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConditionalS3:
    """Replace all backend transport with isolated generated in-memory bytes."""
    client = ConditionalS3()

    def factory(*_args: object, **_kwargs: object) -> ConditionalS3:
        return client

    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("datakeel.storage.objects.boto3.client", factory)
    return client


def test_s3_conditional_create_identical_retry_and_conflict(
    backend: ConditionalS3, tmp_path: Path
) -> None:
    """Repeated identical writes pass; replacing an existing object's bytes always fails."""
    path = tmp_path / "sample.txt"
    path.write_bytes(b"generated")
    store = S3Store("test-bucket")
    assert store.put(path, "aa/sample") == "aa/sample"
    assert store.put(path, "aa/sample") == "aa/sample"
    path.write_bytes(b"replacement")
    with pytest.raises(ConflictError, match="different content"):
        store.put(path, "aa/sample")
    assert backend.objects["aa/sample"] == b"generated"
    assert backend.conditions == ["*", "*", "*"]


def test_s3_immutable_retry_reads_actual_backend_not_cache(
    backend: ConditionalS3, tmp_path: Path
) -> None:
    """Cached matching bytes cannot hide corrupt or conflicting backend content."""
    path = tmp_path / "sample.txt"
    path.write_bytes(b"generated")
    store = S3Store("test-bucket")
    store.put(path, "sample")
    assert store.materialize("sample").read_bytes() == b"generated"
    backend.objects["sample"] = b"tampered!"
    with pytest.raises(ConflictError, match="different content"):
        store.put(path, "sample")
    assert backend.objects["sample"] == b"tampered!"


def test_s3_race_only_one_distinct_content_can_publish(
    backend: ConditionalS3, tmp_path: Path
) -> None:
    """Atomic create conditions choose one winner without overwriting either upload."""
    paths = [tmp_path / "a.bin", tmp_path / "b.bin"]
    paths[0].write_bytes(b"first")
    paths[1].write_bytes(b"second")
    barrier = Barrier(2)

    def publish(path: Path) -> str:
        barrier.wait()
        try:
            S3Store("test-bucket").put(path, "same-key")
        except ConflictError:
            return "conflict"
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(publish, paths))
    assert sorted(results) == ["conflict", "success"]
    assert backend.objects["same-key"] in {b"first", b"second"}


def test_s3_multipart_publication_is_conditional_and_conflict_aborts_parts(
    backend: ConditionalS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Large-object completion uses the same immutable create condition and cleans failed parts."""
    monkeypatch.setattr("datakeel.storage.objects._S3_MULTIPART_THRESHOLD", 4)
    monkeypatch.setattr("datakeel.storage.objects._S3_PART_BYTES", 3)
    path = tmp_path / "sample.bin"
    path.write_bytes(b"generated-bytes")
    store = S3Store("test-bucket")
    store.put(path, "large")
    store.put(path, "large")
    assert backend.objects["large"] == b"generated-bytes"
    assert len(backend.aborted) == 1
    path.write_bytes(b"conflicting-bytes")
    with pytest.raises(ConflictError):
        store.put(path, "large")
    assert len(backend.aborted) == 2
    assert backend.uploads == {}
    assert backend.conditions == ["*", "*", "*"]


def test_s3_multipart_transfer_failure_aborts_without_publication(
    backend: ConditionalS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed multipart uploads leave no published object and no orphaned fixture upload."""
    monkeypatch.setattr("datakeel.storage.objects._S3_MULTIPART_THRESHOLD", 4)
    path = tmp_path / "sample.bin"
    path.write_bytes(b"generated-bytes")
    backend.fail_part = True
    with pytest.raises(ClientError, match="InternalError"):
        S3Store("test-bucket").put(path, "large")
    assert backend.uploads == {}
    assert backend.objects == {}
    assert len(backend.aborted) == 1


def test_s3_unrelated_error_is_not_mistaken_for_existing_object(
    backend: ConditionalS3, tmp_path: Path
) -> None:
    """Permission and transport failures cannot masquerade as an idempotent retry."""
    path = tmp_path / "sample.txt"
    path.write_bytes(b"generated")
    backend.fail_put = True
    with pytest.raises(ClientError, match="AccessDenied"):
        S3Store("test-bucket").put(path, "sample")
    assert backend.objects == {}


def test_s3_acknowledged_corrupt_write_is_refused(
    backend: ConditionalS3, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A backend acknowledgement is checked against actual bytes before callers publish facts."""
    original = backend.put_object

    def corrupt(**parameters: object) -> dict[str, str]:
        result = original(**parameters)
        backend.objects[str(parameters["Key"])] = b"corrupted"
        return result

    monkeypatch.setattr(backend, "put_object", corrupt)
    path = tmp_path / "sample.txt"
    path.write_bytes(b"generated")
    with pytest.raises(ConflictError, match="different content"):
        S3Store("test-bucket").put(path, "sample")


@pytest.mark.parametrize("code", ["NoSuchKey", "AccessDenied"])
def test_s3_conditional_race_missing_object_or_backend_denial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """A conditional race can be retried while unrelated backend failures retain their category."""

    class RacingClient(ConditionalS3):
        def put_object(self, **_parameters: object) -> dict[str, str]:
            raise ClientError({"Error": {"Code": "ConditionalRequestConflict"}}, "PutObject")

        def download_file(self, _bucket: str, key: str, filename: str) -> None:
            raise ClientError({"Error": {"Code": code}}, "GetObject")

    def factory(*_args: object, **_kwargs: object) -> RacingClient:
        return RacingClient()

    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("datakeel.storage.objects.boto3.client", factory)
    path = tmp_path / "sample.txt"
    path.write_bytes(b"generated")
    expected = ConflictError if code == "NoSuchKey" else ClientError
    with pytest.raises(expected):
        S3Store("test-bucket").put(path, "sample")


@pytest.mark.parametrize("code", ["NoSuchKey", "NotFound", "404", "AccessDenied"])
def test_fresh_s3_missing_object_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    """Missing backend objects become unavailable files; permission errors remain failures."""

    class MissingClient(ConditionalS3):
        def download_file(self, _bucket: str, key: str, filename: str) -> None:
            raise ClientError({"Error": {"Code": code}}, "GetObject")

    def factory(*_args: object, **_kwargs: object) -> MissingClient:
        return MissingClient()

    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("datakeel.storage.objects.boto3.client", factory)
    expected = ClientError if code == "AccessDenied" else FileNotFoundError
    with pytest.raises(expected), fresh_object(S3Store("test-bucket"), "sample"):
        pytest.fail("missing objects have no materialized bytes")
