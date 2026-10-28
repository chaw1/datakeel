# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded numeric encoding helpers shared by PLY and PCD."""

from io import BytesIO
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud.models import CloudField, PointCloud

MAX_POINTS = 10_000_000
MAX_HEADER_BYTES = 1_048_576
MAX_FILE_BYTES = 2_147_483_648
MAX_SCALAR_FIELDS = 1024


def structured_dtype(
    fields: tuple[CloudField, ...], endian: Literal["<", ">"] = "<"
) -> np.dtype[np.void]:
    """Construct a packed structured dtype while retaining vector-valued fields."""
    if len({field.name for field in fields}) != len(fields):
        msg = "Point-cloud field names must be unique"
        raise ValidationError(msg)
    if not fields or sum(field.count for field in fields) > MAX_SCALAR_FIELDS:
        msg = f"Point-cloud schema must contain 1 to {MAX_SCALAR_FIELDS} scalar fields"
        raise ValidationError(msg)
    return np.dtype(
        [
            (field.name, np.dtype(field.dtype).newbyteorder(endian), (field.count,))
            if field.count != 1
            else (field.name, np.dtype(field.dtype).newbyteorder(endian))
            for field in fields
        ]
    )


def read_values(
    body: bytes, fields: tuple[CloudField, ...], count: int, encoding: str
) -> NDArray[np.void]:
    """Read a declared number of packed rows and reject truncated or malformed values."""
    if not 0 <= count <= MAX_POINTS:
        msg = f"Point count must be between 0 and {MAX_POINTS}"
        raise ValidationError(msg)
    dtype = structured_dtype(fields, ">" if encoding == "binary_big_endian" else "<")
    if count == 0:
        return np.empty(0, dtype=dtype)
    if encoding == "ascii" and not body.strip():
        msg = "Point-cloud row count does not match its header"
        raise ValidationError(msg)
    try:
        values = (
            np.loadtxt(BytesIO(body), dtype=dtype, ndmin=1, comments=None, max_rows=count)
            if encoding == "ascii"
            else np.frombuffer(body, dtype=dtype, count=count)
        )
    except (ValueError, TypeError, OverflowError) as exc:
        msg = "Malformed or truncated point-cloud data"
        raise ValidationError(msg) from exc
    if len(values) != count:
        msg = "Point-cloud row count does not match its header"
        raise ValidationError(msg)
    return values


def encode_values(cloud: PointCloud, encoding: str) -> bytes:
    """Encode source fields exactly, preserving integer and vector values."""
    if encoding != "ascii":
        dtype = structured_dtype(cloud.fields, ">" if encoding == "binary_big_endian" else "<")
        return cloud.data.astype(dtype, copy=False).tobytes()
    columns: list[NDArray[np.str_]] = []
    for field in cloud.fields:
        values = cloud.data[field.name].reshape(len(cloud.data), field.count)
        fmt = "%.17g" if np.dtype(field.dtype).kind == "f" else "%d"
        columns.extend(np.char.mod(fmt, values[:, index]) for index in range(field.count))
    lines = columns[0]
    for column in columns[1:]:
        lines = np.char.add(np.char.add(lines, " "), column)
    return ("\n".join(lines.tolist()) + ("\n" if len(lines) else "")).encode("ascii")


def header_lines(content: bytes, terminator: bytes) -> tuple[list[str], bytes]:
    """Separate a bounded ASCII header from its opaque binary or text payload."""
    stream = BytesIO(content)
    lines: list[str] = []
    while stream.tell() < MAX_HEADER_BYTES:
        line = stream.readline(MAX_HEADER_BYTES + 1)
        if not line:
            break
        try:
            lines.append(line.decode("ascii").strip())
        except UnicodeDecodeError as exc:
            msg = "Point-cloud header must be ASCII"
            raise ValidationError(msg) from exc
        if line.strip().split(maxsplit=1)[0:1] == [terminator]:
            return lines, content[stream.tell() :]
    msg = "Missing or oversized point-cloud header"
    raise ValidationError(msg)
