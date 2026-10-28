# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and write ASCII and both standard binary PLY encodings."""

from typing import cast

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud.codec import encode_values, header_lines, read_values
from datakeel.operators.pointcloud.models import CloudField, Encoding, PointCloud

_TYPES = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "i2",
    "int16": "i2",
    "ushort": "u2",
    "uint16": "u2",
    "int": "i4",
    "int32": "i4",
    "uint": "u4",
    "uint32": "u4",
    "float": "f4",
    "float32": "f4",
    "double": "f8",
    "float64": "f8",
}
_NAMES = {
    "i1": "char",
    "u1": "uchar",
    "i2": "short",
    "u2": "ushort",
    "i4": "int",
    "u4": "uint",
    "f4": "float",
    "f8": "double",
}
_ENCODINGS = {"ascii", "binary_little_endian", "binary_big_endian"}
_DECLARATION_WIDTH = 3


def _vertex_fields(lines: list[str]) -> tuple[tuple[CloudField, ...], int]:
    fields: list[CloudField] = []
    count = -1
    element = ""
    for line in lines:
        tokens = line.split()
        if tokens[:1] == ["element"]:
            if len(tokens) != _DECLARATION_WIDTH or (count < 0 and element):
                msg = "PLY vertices must be the first data element"
                raise ValidationError(msg)
            element = tokens[1]
            if element == "vertex":
                count = int(tokens[2])
        elif tokens[:1] == ["property"] and element == "vertex":
            if len(tokens) != _DECLARATION_WIDTH or tokens[1] not in _TYPES:
                msg = "Unsupported PLY vertex property; scalar numeric fields are required"
                raise ValidationError(msg)
            fields.append(CloudField(name=tokens[2], dtype=_TYPES[tokens[1]]))
    if count < 0:
        msg = "PLY header has no vertex element"
        raise ValidationError(msg)
    return tuple(fields), count


def loads(content: bytes) -> PointCloud:
    """Parse PLY vertices while safely ignoring subsequent mesh elements."""
    lines, body = header_lines(content, b"end_header")
    formats = [line.split() for line in lines if line.startswith("format ")]
    if lines[0] != "ply" or len(formats) != 1 or len(formats[0]) != _DECLARATION_WIDTH:
        msg = "Invalid PLY signature or format declaration"
        raise ValidationError(msg)
    encoding = formats[0][1]
    if encoding not in _ENCODINGS or formats[0][2] != "1.0":
        msg = "Unsupported PLY encoding or version"
        raise ValidationError(msg)
    try:
        fields, count = _vertex_fields(lines)
    except ValueError as exc:
        msg = "Invalid PLY vertex header"
        raise ValidationError(msg) from exc
    return PointCloud(
        format="ply",
        encoding=cast("Encoding", encoding),
        fields=fields,
        data=read_values(body, fields, count, encoding),
    )


def dumps(cloud: PointCloud, encoding: Encoding | None = None) -> bytes:
    """Write a portable vertex-only PLY file with original scalar field types."""
    selected = encoding or cloud.encoding
    if selected not in _ENCODINGS:
        msg = "Unsupported PLY output encoding"
        raise ValidationError(msg)
    if any(field.count != 1 or field.dtype.lstrip("<>=|") not in _NAMES for field in cloud.fields):
        msg = "PLY output supports standard scalar field types only"
        raise ValidationError(msg)
    properties = [
        f"property {_NAMES[field.dtype.lstrip('<>=|')]} {field.name}" for field in cloud.fields
    ]
    header = [
        "ply",
        f"format {selected} 1.0",
        f"element vertex {len(cloud.data)}",
        *properties,
        "end_header",
        "",
    ]
    return "\n".join(header).encode("ascii") + encode_values(cloud, selected)
