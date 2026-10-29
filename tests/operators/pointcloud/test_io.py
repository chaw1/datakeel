# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify independent format variants, field preservation and malformed inputs."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import numpy as np
import pytest
from pydantic import ValidationError as PydanticValidationError

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud import pcd, ply
from datakeel.operators.pointcloud.codec import header_lines, read_values
from datakeel.operators.pointcloud.io import dump_cloud, load_cloud
from datakeel.operators.pointcloud.models import CloudField, PointCloud
from tests.operators.pointcloud.helpers import make_cloud

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.operators.pointcloud.models import Encoding


@pytest.mark.parametrize("encoding", ["ascii", "binary_little_endian", "binary_big_endian"])
def test_ply_roundtrip_all_encodings_preserves_numeric_fields(encoding: Encoding) -> None:
    """Retain float, intensity, packed RGB and integer labels in every PLY encoding."""
    source = make_cloud(np.random.default_rng(7).normal(size=(11, 3)), encoding)
    result = ply.loads(ply.dumps(source))
    assert result.fields == source.fields
    assert result.encoding == encoding
    np.testing.assert_array_equal(result.data, source.data)
    assert not result.data.flags.writeable


@pytest.mark.parametrize("encoding", ["ascii", "binary"])
def test_pcd_roundtrip_all_encodings_preserves_numeric_fields(encoding: Encoding) -> None:
    """Read independent PCD headers and preserve packed colors without float conversion."""
    source = make_cloud(np.random.default_rng(8).normal(size=(11, 3)))
    cloud = source.model_copy(update={"format": "pcd", "encoding": encoding})
    result = pcd.loads(pcd.dumps(cloud))
    np.testing.assert_array_equal(result.data, source.data)
    assert result.encoding == encoding


@pytest.mark.parametrize("encoding", ["ascii", "binary"])
def test_pcd_vector_fields_and_uint64_roundtrip_are_exact(encoding: Encoding) -> None:
    """Preserve vector COUNT fields and integers larger than floating-point precision."""
    fields = tuple(
        CloudField(name=name, dtype=dtype, count=count)
        for name, dtype, count in (
            ("x", "f4", 1),
            ("y", "f4", 1),
            ("z", "f4", 1),
            ("normal", "f4", 3),
            ("label", "u8", 1),
        )
    )
    data = np.zeros(
        2, dtype=[("x", "f4"), ("y", "f4"), ("z", "f4"), ("normal", "f4", (3,)), ("label", "u8")]
    )
    data["normal"] = [[1, 0, 0], [0, 0, 1]]
    data["label"] = [2**63 + 13, 2**63 + 27]
    cloud = PointCloud(format="pcd", encoding=encoding, fields=fields, data=data)
    np.testing.assert_array_equal(pcd.loads(pcd.dumps(cloud)).data, data)


def test_independent_binary_ply_fixture_reads_big_endian_coordinates() -> None:
    """Do not rely solely on the writer to verify endianness."""
    content = (
        b"ply\nformat binary_big_endian 1.0\nelement vertex 1\n"
        b"property float x\nproperty float y\nproperty float z\nend_header\n"
    )
    cloud = ply.loads(content + struct.pack(">fff", 1.25, -2.5, 3.75))
    np.testing.assert_array_equal(cloud.xyz, [[1.25, -2.5, 3.75]])


def test_ascii_ply_ignores_faces_after_vertices() -> None:
    """A mesh vertex stream remains valid input without interpreting face lists."""
    content = (
        b"ply\nformat ascii 1.0\nelement vertex 1\nproperty float x\n"
        b"property float y\nproperty float z\nelement face 1\n"
        b"property list uchar int vertex_indices\nend_header\n1 2 3\n3 0 0 0\n"
    )
    np.testing.assert_array_equal(ply.loads(content).xyz, [[1, 2, 3]])


@pytest.mark.parametrize(
    "content",
    [
        b"ply\nformat ascii 1.0\nend_header\n",
        b"ply\nformat other 1.0\nend_header\n",
        b"ply\nformat ascii 2.0\nend_header\n",
        b"ply\nformat ascii 1.0\nelement vertex no\nend_header\n",
        b"ply\nformat ascii 1.0\nelement face 1\nelement vertex 1\nend_header\n",
        b"ply\nformat ascii 1.0\nelement vertex 1\nproperty list float x\nend_header\n",
        b"FIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nWIDTH 1\nHEIGHT 1\nDATA binary_compressed\n",
        b"FIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nWIDTH 1\nHEIGHT 1\nDATA unknown\n",
        b"FIELDS x y z\nSIZE 4\nTYPE F F F\nWIDTH 1\nHEIGHT 1\nDATA ascii\n",
        b"FIELDS x y z\nSIZE 3 4 4\nTYPE F F F\nWIDTH 1\nHEIGHT 1\nDATA ascii\n",
        b"FIELDS x y z\nSIZE 4 4 4\nTYPE X F F\nWIDTH 1\nHEIGHT 1\nDATA ascii\n",
        b"FIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nCOUNT 0 1 1\nWIDTH 1\nHEIGHT 1\nDATA ascii\n",
        b"FIELDS x y z\nFIELDS x y z\nDATA ascii\n",
        b"FIELDS x y z\nSIZE 4 4 4\nTYPE F F F\nWIDTH 1\nHEIGHT 1\nPOINTS 2\nDATA ascii\n",
    ],
)
def test_malformed_cloud_headers_fail_explicitly(content: bytes) -> None:
    """Corrupt declarations and unsupported encodings never masquerade as empty clouds."""
    with pytest.raises(ValidationError):
        (ply.loads if content.startswith(b"ply") else pcd.loads)(content)


@pytest.mark.parametrize(
    ("body", "count"), [(b"", 1), (b"x y z\n", 1), (b"", -1), (b"", 10_000_001)]
)
def test_data_count_and_malformed_values_are_rejected(body: bytes, count: int) -> None:
    """Bound decoded rows and reject malformed numeric payloads."""
    fields = tuple(CloudField(name=name, dtype="f4") for name in ("x", "y", "z"))
    with pytest.raises(ValidationError):
        read_values(body, fields, count, "ascii")


def test_truncated_binary_cloud_fails_explicitly() -> None:
    """Require every declared binary point to have a complete packed record."""
    cloud = make_cloud(np.ones((3, 3)))
    with pytest.raises(ValidationError, match="truncated"):
        ply.loads(ply.dumps(cloud)[:-1])


def test_header_bounds_and_ascii_validation_reject_unterminated_input() -> None:
    """Do not scan indefinitely or consume arbitrary binary as a text header."""
    for content in (b"no header\n", b"\xff\n"):
        with pytest.raises(ValidationError):
            header_lines(content, b"DATA")


@pytest.mark.parametrize("encoding", ["ascii", "binary_little_endian"])
def test_empty_cloud_roundtrip_retains_schema(encoding: Encoding) -> None:
    """Represent empty but valid point streams without inventing coordinates."""
    cloud = make_cloud(np.empty((0, 3)), encoding)
    assert len(ply.loads(ply.dumps(cloud)).data) == 0


def test_io_detects_content_and_writes_original_format(tmp_path: Path) -> None:
    """File suffixes cannot change binary decoding semantics."""
    cloud = make_cloud(np.eye(3))
    path = tmp_path / "arbitrary.dat"
    path.write_bytes(dump_cloud(cloud))
    np.testing.assert_array_equal(load_cloud(path).data, cloud.data)


def test_boundary_rejects_unknown_fields_and_missing_xyz() -> None:
    """Freeze schemas and arrays at the point-cloud module boundary."""
    with pytest.raises(PydanticValidationError):
        CloudField.model_validate({"name": "x", "dtype": "f4", "surprise": True})
    with pytest.raises(PydanticValidationError, match="require x"):
        PointCloud(
            format="ply",
            encoding="ascii",
            fields=(CloudField(name="x", dtype="f4"),),
            data=np.zeros(1, dtype=[("x", "f4")]),
        )
