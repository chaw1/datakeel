# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""In-memory conditional S3 operations with bounded multipart fixtures."""

from pathlib import Path
from threading import Lock
from typing import BinaryIO, cast
from uuid import uuid4

from botocore.exceptions import ClientError


class ConditionalS3:
    """Implement conditional publication, fresh downloads and multipart cleanup locally."""

    def __init__(self) -> None:
        """Keep generated backend bytes and uploaded parts independent of local caches."""
        self.objects: dict[str, bytes] = {}
        self.uploads: dict[str, list[bytes]] = {}
        self.conditions: list[str] = []
        self.aborted: list[str] = []
        self.fail_part = False
        self.fail_put = False
        self.lock = Lock()

    def put_object(self, **parameters: object) -> dict[str, str]:
        """Publish only if no object exists, simulating the backend's atomic condition."""
        if self.fail_put:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")
        source = cast("BinaryIO", parameters["Body"])
        self._publish(str(parameters["Key"]), source.read(), str(parameters["IfNoneMatch"]))
        return {}

    def _publish(self, key: str, content: bytes, condition: str) -> None:
        with self.lock:
            self.conditions.append(condition)
            if condition != "*":
                message = "Missing immutable create condition"
                raise ValueError(message)
            if key in self.objects:
                raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
            self.objects[key] = content

    def download_file(self, _bucket: str, key: str, filename: str) -> None:
        """Materialize current backend bytes, including externally injected corruption."""
        Path(filename).write_bytes(self.objects[key])

    def create_multipart_upload(self, **_parameters: object) -> dict[str, str]:
        """Create independent unpublished multipart state."""
        identifier = uuid4().hex
        self.uploads[identifier] = []
        return {"UploadId": identifier}

    def upload_part(self, **parameters: object) -> dict[str, str]:
        """Append bounded ordered bytes or inject a part transfer failure."""
        if self.fail_part:
            raise ClientError({"Error": {"Code": "InternalError"}}, "UploadPart")
        content = parameters["Body"]
        assert isinstance(content, bytes)
        self.uploads[str(parameters["UploadId"])].append(content)
        return {"ETag": str(parameters["PartNumber"])}

    def complete_multipart_upload(self, **parameters: object) -> dict[str, str]:
        """Apply the create condition at atomic multipart publication, preserving existing bytes."""
        identifier = str(parameters["UploadId"])
        self._publish(
            str(parameters["Key"]),
            b"".join(self.uploads[identifier]),
            str(parameters["IfNoneMatch"]),
        )
        del self.uploads[identifier]
        return {}

    def abort_multipart_upload(self, **parameters: object) -> dict[str, str]:
        """Drop only the caller's failed unpublished multipart state."""
        identifier = str(parameters["UploadId"])
        self.aborted.append(identifier)
        del self.uploads[identifier]
        return {}
