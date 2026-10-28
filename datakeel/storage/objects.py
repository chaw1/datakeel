# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed local and S3 object backends."""

import hashlib
import os
import shutil
import tempfile
from collections.abc import Generator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
    from mypy_boto3_s3.type_defs import CompletedPartTypeDef
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.settings import get_settings
from datakeel.storage.database import data_dir

_S3_MULTIPART_THRESHOLD = 64 * 1024 * 1024
_S3_PART_BYTES = 8 * 1024 * 1024
_S3_MAX_PARTS = 10_000


def digest(path: Path) -> str:
    """Compute a content-addressable SHA-256 digest from disk."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_key(key: str) -> str:
    """Reject keys that could escape the configured object root."""
    if not key or Path(key).is_absolute() or ".." in Path(key).parts or "\\" in key:
        message = "Invalid object key"
        raise ValidationError(message)
    return key


class ObjectStore(Protocol):
    """Minimal object persistence and materialization contract."""

    def put(self, path: Path, key: str) -> str:
        """Persist a local object under a validated key."""
        ...

    def materialize(self, key: str) -> Path:
        """Return a locally readable path for an object."""
        ...


class LocalStore:
    """Atomically publish immutable objects on the local filesystem."""

    def __init__(self, root: Path | None = None) -> None:
        """Initialize a private object directory."""
        self.root = (root or data_dir() / "objects").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, path: Path, key: str) -> str:
        """Publish content through an independent temporary file."""
        destination = self.root / safe_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.resolve().is_relative_to(self.root) or destination.is_symlink():
            message = "Object outside store"
            raise ValidationError(message)
        checksum = digest(path)
        if destination.exists():
            self._verify_existing(destination, checksum)
            return key
        temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
        try:
            shutil.copyfile(path, temporary)
            self._verify_existing(temporary, checksum)
            try:
                os.link(temporary, destination)
            except FileExistsError:
                self._verify_existing(destination, checksum)
        finally:
            temporary.unlink(missing_ok=True)
        return key

    @staticmethod
    def _verify_existing(path: Path, checksum: str) -> None:
        if path.is_symlink() or digest(path) != checksum:
            message = "Immutable object already exists with different content"
            raise ConflictError(message)

    def materialize(self, key: str) -> Path:
        """Resolve an object, downloading into the cache when necessary."""
        path = (self.root / safe_key(key)).resolve()
        if not path.is_relative_to(self.root):
            message = "Object outside store"
            raise ValidationError(message)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path


class _S3Factory(Protocol):
    def client(self, service_name: Literal["s3"], *, endpoint_url: str | None) -> "S3Client": ...


class S3Store:
    """Persist objects in S3 and cache downloads locally."""

    def __init__(self, bucket: str, endpoint_url: str | None = None) -> None:
        """Connect to an explicitly configured S3-compatible bucket."""
        self.bucket = bucket
        self.client = cast("_S3Factory", boto3).client("s3", endpoint_url=endpoint_url)
        self.cache = data_dir() / "object-cache"

    def put(self, path: Path, key: str) -> str:
        """Conditionally create immutable bytes; accept retries only after a fresh hash check."""
        key = safe_key(key)
        checksum = digest(path)
        try:
            if path.stat().st_size >= _S3_MULTIPART_THRESHOLD:
                self._multipart(path, key)
            else:
                with path.open("rb") as source:
                    self.client.put_object(
                        Bucket=self.bucket, Key=key, Body=source, IfNoneMatch="*"
                    )
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}:
                raise
        self._verify_existing(key, checksum)
        return key

    def _verify_existing(self, key: str, checksum: str) -> None:
        try:
            with fresh_object(self, key) as actual:
                if digest(actual) != checksum:
                    message = "Immutable object already exists with different content"
                    raise ConflictError(message)
        except FileNotFoundError as error:
            message = "Object publication changed concurrently; retry the upload"
            raise ConflictError(message) from error

    def _multipart(self, path: Path, key: str) -> None:
        upload = self.client.create_multipart_upload(Bucket=self.bucket, Key=key)
        identifier = upload["UploadId"]
        complete = False
        try:
            parts = self._upload_parts(path, key, identifier)
            self.client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=identifier,
                MultipartUpload={"Parts": parts},
                IfNoneMatch="*",
            )
            complete = True
        finally:
            if not complete:
                with suppress(ClientError):
                    self.client.abort_multipart_upload(
                        Bucket=self.bucket, Key=key, UploadId=identifier
                    )

    def _upload_parts(self, path: Path, key: str, identifier: str) -> "list[CompletedPartTypeDef]":
        parts: list[CompletedPartTypeDef] = []
        part_bytes = max(_S3_PART_BYTES, (path.stat().st_size + _S3_MAX_PARTS - 1) // _S3_MAX_PARTS)
        with path.open("rb") as source:
            while content := source.read(part_bytes):
                ordinal = len(parts) + 1
                part = self.client.upload_part(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=identifier,
                    PartNumber=ordinal,
                    Body=content,
                )
                parts.append({"ETag": part["ETag"], "PartNumber": ordinal})
        return parts

    def materialize(self, key: str) -> Path:
        """Resolve an object, downloading into the cache when necessary."""
        path = self.cache / safe_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
            try:
                self.client.download_file(self.bucket, key, str(temporary))
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return path


def object_store() -> ObjectStore:
    """Build the backend selected by the validated process settings."""
    settings = get_settings()
    bucket = settings.s3_bucket
    return S3Store(bucket, settings.s3_endpoint) if bucket else LocalStore()


@contextmanager
def fresh_object(store: ObjectStore, key: str) -> Generator[Path]:
    """Read actual backend bytes, bypassing any previously materialized S3 cache."""
    if not isinstance(store, S3Store):
        yield store.materialize(key)
        return
    with tempfile.TemporaryDirectory(prefix="datakeel-object-check-") as directory:
        path = Path(directory) / "object"
        try:
            store.client.download_file(store.bucket, safe_key(key), str(path))
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"NoSuchKey", "NotFound", "404"}:
                raise
            raise FileNotFoundError(key) from error
        yield path
