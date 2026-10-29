# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and write PCD 0.7 ASCII and uncompressed binary point records."""

from typing import cast

import numpy as np

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud.codec import encode_values, header_lines, read_values
from datakeel.operators.pointcloud.models import CloudField, Encoding, PointCloud


def _fields(header: dict[str, list[str]]) -> tuple[CloudField, ...]:
    names, sizes, kinds = header["FIELDS"], header["SIZE"], header["TYPE"]
    counts = header.get("COUNT", ["1"] * len(names))
    if not len(names) == len(sizes) == len(kinds) == len(counts):
        msg = "PCD field declarations must have matching lengths"
        raise ValidationError(msg)
    fields: list[CloudField] = []
    for name, size, kind, count in zip(names, sizes, kinds, counts, strict=True):
        dtype = f"{kind.lower()}{int(size)}"
        if kind not in {"F", "I", "U"} or int(count) < 1:
            msg = "Unsupported PCD field type or count"
            raise ValidationError(msg)
        if dtype not in {"i1", "i2", "i4", "i8", "u1", "u2", "u4", "u8", "f4", "f8"}:
            msg = "Unsupported PCD numeric field width"
            raise ValidationError(msg)
        fields.append(CloudField(name=name, dtype=dtype, count=int(count)))
    return tuple(fields)


def _header(lines: list[str]) -> dict[str, list[str]]:
    header: dict[str, list[str]] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        key, *values = line.split()
        if key in header:
            msg = "Duplicate PCD header declaration"
            raise ValidationError(msg)
        header[key] = values
    return header


def loads(content: bytes) -> PointCloud:
    """Parse PCD records and explicitly reject compressed payloads."""
    lines, body = header_lines(content, b"DATA")
    header = _header(lines)
    try:
        encoding = header["DATA"][0]
        if encoding == "binary_compressed":
            msg = "PCD binary_compressed is not supported"
            raise ValidationError(msg)
        if encoding not in {"ascii", "binary"}:
            msg = "Unsupported PCD encoding"
            raise ValidationError(msg)
        count = int(
            header.get("POINTS", [str(int(header["WIDTH"][0]) * int(header["HEIGHT"][0]))])[0]
        )
        if int(header["WIDTH"][0]) * int(header["HEIGHT"][0]) != count:
            msg = "PCD WIDTH, HEIGHT and POINTS disagree"
            raise ValidationError(msg)
        fields = _fields(header)
    except (KeyError, IndexError, ValueError) as exc:
        msg = f"Invalid PCD header: {exc}"
        raise ValidationError(msg) from exc
    return PointCloud(
        format="pcd",
        encoding=cast("Encoding", encoding),
        fields=fields,
        data=read_values(body, fields, count, encoding),
    )


def dumps(cloud: PointCloud, encoding: Encoding | None = None) -> bytes:
    """Write a little-endian packed or ASCII PCD with all declared fields."""
    selected = encoding or cloud.encoding
    if selected not in {"ascii", "binary"}:
        msg = "Unsupported PCD output encoding"
        raise ValidationError(msg)
    fields = cloud.fields
    header = [
        "# .PCD v0.7",
        "VERSION .7",
        "FIELDS " + " ".join(field.name for field in fields),
        "SIZE " + " ".join(str(np.dtype(field.dtype).itemsize) for field in fields),
        "TYPE " + " ".join(np.dtype(field.dtype).kind.upper() for field in fields),
        "COUNT " + " ".join(str(field.count) for field in fields),
        f"WIDTH {len(cloud.data)}",
        "HEIGHT 1",
        "VIEWPOINT 0 0 0 1 0 0 0",
        f"POINTS {len(cloud.data)}",
        f"DATA {selected}",
        "",
    ]
    return "\n".join(header).encode("ascii") + encode_values(cloud, selected)
