# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check the container supervisor's host-safe helpers; its kill path never runs on the host."""

import json
import os
from pathlib import Path

import pytest

from datakeel import sandbox_entry


def test_supervisor_refuses_to_run_outside_a_private_pid_namespace() -> None:
    """The namespace-wide kill cannot be reached from an ordinary host process."""
    assert os.getpid() != 1
    with pytest.raises(RuntimeError, match="outside a private sandbox PID namespace"):
        sandbox_entry.stop_all_processes()
    with pytest.raises(SystemExit, match="PID 1"):
        sandbox_entry.main()


def test_read_regular_rejects_links_special_and_oversized_files(tmp_path: Path) -> None:
    """Hostile declaration placeholders neither block nor redirect the supervisor."""
    regular = tmp_path / "regular"
    regular.write_bytes(b"[]")
    link = tmp_path / "link"
    link.symlink_to(regular)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert sandbox_entry.read_regular(regular, 2) == b"[]"
    assert sandbox_entry.read_regular(regular, 1) is None
    assert sandbox_entry.read_regular(link, 2) is None
    assert sandbox_entry.read_regular(fifo, 2) is None
    assert sandbox_entry.read_regular(tmp_path / "missing", 2) is None


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, ([], "completed")),
        (b'[{"path": "a", "metadata": {}}]', ([{"path": "a", "metadata": {}}], "completed")),
        (b"not json", ([], "invalid_output")),
        (b"[" * 60000, ([], "invalid_output")),
    ],
)
def test_declared_outputs_forward_only_decodable_declarations(
    tmp_path: Path, content: bytes | None, expected: tuple[object, str]
) -> None:
    """A missing declaration means no outputs; malformed or hostile JSON fails the run."""
    path = tmp_path / "result.json"
    if content is not None:
        path.write_bytes(content)
    assert sandbox_entry.declared_outputs(path) == expected


def test_declared_outputs_reject_symlinked_declaration(tmp_path: Path) -> None:
    """A dangling or redirected declaration link is invalid rather than an empty success."""
    path = tmp_path / "result.json"
    path.symlink_to(tmp_path / "missing-target")
    assert sandbox_entry.declared_outputs(path) == ([], "invalid_output")


def test_publish_status_writes_complete_record_without_leftovers(tmp_path: Path) -> None:
    """The supervisor record appears atomically and its temporary file is removed."""
    sandbox_entry.publish_status({"exit_code": 0, "reason": "timeout", "outputs": []}, tmp_path)
    assert [path.name for path in tmp_path.iterdir()] == ["status.json"]
    assert json.loads((tmp_path / "status.json").read_text())["reason"] == "timeout"


@pytest.mark.parametrize("kind", ["regular", "symlink", "directory"])
def test_publish_status_never_replaces_a_worker_record(tmp_path: Path, kind: str) -> None:
    """A forged or hostile record stays for the host to freeze or reject."""
    target = tmp_path / "status.json"
    if kind == "regular":
        target.write_text("forged")
    elif kind == "symlink":
        target.symlink_to("/etc/passwd")
    else:
        target.mkdir()
    sandbox_entry.publish_status({"exit_code": 0, "reason": "completed", "outputs": []}, tmp_path)
    assert [path.name for path in tmp_path.iterdir()] == ["status.json"]
    assert target.is_symlink() == (kind == "symlink")
    if kind == "regular":
        assert target.read_text() == "forged"
