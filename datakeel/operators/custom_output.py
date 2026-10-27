# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate untrusted output archives without extracting their filesystem entries."""

import io
import tarfile
from pathlib import PurePosixPath

from pydantic import Field, JsonValue
from pydantic import ValidationError as ModelValidationError

from datakeel.core.custom_sandbox import SandboxOutput, SandboxRequest
from datakeel.core.custom_schema import validate_custom_values
from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel, JsonDocument

_MAXIMUM_STATUS = 65536


class OutputRejectedError(ValidationError):
    """Reject an entire output set before publication."""


class OutputDeclaration(BoundaryModel):
    """Accept only a basename and schema-checked JSON metadata from user code."""

    path: str = Field(min_length=1, max_length=255)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class WorkerStatus(BoundaryModel):
    """Describe the untrusted worker completion message."""

    exit_code: int
    outputs: tuple[OutputDeclaration, ...] = ()
    reason: str = "completed"


def validate_schema(schema: dict[str, JsonValue], value: dict[str, JsonValue]) -> None:
    """Validate the restricted schema vocabulary without reference or regex execution."""
    try:
        validate_custom_values(JsonDocument(schema), JsonDocument(value))
    except ValidationError as error:
        msg = "Value does not match the frozen JSON schema"
        raise OutputRejectedError(msg) from error


def parse_status(content: bytes) -> WorkerStatus:
    """Parse a bounded completion record while rejecting unknown fields."""
    if len(content) > _MAXIMUM_STATUS:
        msg = "Worker status exceeds the allowed size"
        raise OutputRejectedError(msg)
    try:
        return WorkerStatus.model_validate_json(content)
    except ModelValidationError as error:
        msg = "Worker returned an invalid completion record"
        raise OutputRejectedError(msg) from error


def archive_files(content: bytes, maximum: int) -> dict[str, bytes]:
    """Read flat regular files only; never extract an untrusted tar archive."""
    files: dict[str, bytes] = {}
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:") as archive:
            for member in archive:
                path = PurePosixPath(member.name)
                if (
                    member.isdir()
                    and len(path.parts) <= 1
                    and not path.is_absolute()
                    and ".." not in path.parts
                ):
                    continue
                _validate_member(member, maximum)
                name = path.name
                stream = archive.extractfile(member)
                if stream is None or name in files:
                    msg = "Missing or duplicate output file"
                    raise OutputRejectedError(msg)
                files[name] = stream.read(maximum + 1)
                total += len(files[name])
                if total > maximum:
                    msg = "Output archive exceeds the total byte limit"
                    raise OutputRejectedError(msg)
    except (tarfile.TarError, OSError) as error:
        msg = "Invalid output archive"
        raise OutputRejectedError(msg) from error
    return files


def _validate_member(member: tarfile.TarInfo, maximum: int) -> None:
    path = PurePosixPath(member.name)
    if (
        not member.isreg()
        or path.is_absolute()
        or len(path.parts) not in {1, 2}
        or ".." in path.parts
        or "\\" in member.name
        or member.size > maximum
        or member.size < 0
    ):
        msg = "Output must contain flat regular files without links"
        raise OutputRejectedError(msg)


def validated_outputs(
    files: dict[str, bytes], status: WorkerStatus, request: SandboxRequest
) -> tuple[SandboxOutput, ...]:
    """Accept a complete matching file set and reject every invalid run atomically."""
    limits = request.limits
    names = [declaration.path for declaration in status.outputs]
    if len(names) > limits.max_output_files or len(names) != len(set(names)):
        msg = "Output file count exceeds the limit or contains duplicates"
        raise OutputRejectedError(msg)
    if set(files) != set(names):
        msg = "Output files do not match the declared output manifest"
        raise OutputRejectedError(msg)
    outputs: list[SandboxOutput] = []
    for declaration in status.outputs:
        name = declaration.path
        if name in {".", ".."} or "/" in name or "\\" in name:
            msg = "Output paths must be basenames"
            raise OutputRejectedError(msg)
        content = files[name]
        if len(content) > limits.max_file_bytes:
            msg = "Output file exceeds the per-file limit"
            raise OutputRejectedError(msg)
        validate_schema(request.metadata_schema, declaration.metadata)
        outputs.append(SandboxOutput(name=name, content=content, metadata=declaration.metadata))
    if sum(len(item.content) for item in outputs) > limits.max_output_bytes:
        msg = "Output files exceed the total byte limit"
        raise OutputRejectedError(msg)
    return tuple(outputs)
