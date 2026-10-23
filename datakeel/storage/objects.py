# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Content-addressed local and S3 object backends."""

import hashlib
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, cast

if TYPE_CHECKING:
    from mypy_boto3_s3.client import S3Client
from uuid import uuid4

import boto3

from datakeel.core.errors import ValidationError
from datakeel.core.settings import get_settings
from datakeel.storage.database import data_dir


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
        self.root = root or data_dir() / "objects"
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, path: Path, key: str) -> str:
        """Publish content through an independent temporary file."""
        destination = self.root / safe_key(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
            try:
                shutil.copyfile(path, temporary)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        return key

    def materialize(self, key: str) -> Path:
        """Resolve an object, downloading into the cache when necessary."""
        path = (self.root / safe_key(key)).resolve()
        if not path.is_relative_to(self.root.resolve()):
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
        """Upload one file to the configured bucket."""
        self.client.upload_file(str(path), self.bucket, safe_key(key))
        return key

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
