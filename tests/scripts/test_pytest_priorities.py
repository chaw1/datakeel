# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Scheduling hints preserve the complete test collection and its existing metadata."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from scripts import pytest_priorities

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class _Item:
    nodeid: str
    identity: str = "generated"
    marks: tuple[pytest.MarkDecorator, ...] = ()


def _prioritize(items: list[_Item]) -> None:
    pytest_priorities.prioritize_tests(cast("list[pytest.Item]", items))


def test_hints_are_unique_complete_repository_test_nodes() -> None:
    """Every static hint points to a real test function through its complete node ID."""
    hints = pytest_priorities.PRIORITY_NODEIDS
    assert len(hints) == len(set(hints))
    for nodeid in hints:
        relative, separator, name = nodeid.partition("::")
        assert separator
        assert relative.startswith("tests/")
        assert name.startswith("test_")
        path = ROOT / relative
        assert path.is_file(), nodeid
        functions = {
            node.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert name in functions, nodeid


def test_hinted_cases_start_first_and_unknown_cases_keep_relative_order() -> None:
    """A late collected long case can start early without permuting ordinary cases."""
    first, second = [_Item(nodeid) for nodeid in pytest_priorities.PRIORITY_NODEIDS[:2]]
    unknown = [_Item(f"tests/test_generated.py::test_case[{index}]") for index in range(3)]
    items = [unknown[0], second, unknown[1], first, unknown[2]]
    _prioritize(items)
    assert items == [first, second, *unknown]


def test_unknown_cases_remain_in_collection_order() -> None:
    """A collection with no matching hints retains every item in its original position."""
    items = [_Item(f"tests/test_generated.py::test_case[{index}]") for index in (8, 2, 5)]
    original = tuple(items)
    _prioritize(items)
    assert tuple(items) == original


def test_similar_function_names_and_new_parameters_require_exact_hints() -> None:
    """Prefixes and parametrized variants cannot accidentally inherit an unrelated hint."""
    nodeid = pytest_priorities.PRIORITY_NODEIDS[0]
    unknown = [_Item(nodeid + suffix) for suffix in ("_extra", "[generated]", "@another-group")]
    exact = _Item(nodeid)
    items = [unknown[0], exact, *unknown[1:]]
    _prioritize(items)
    assert items == [exact, *unknown]


def test_duplicate_nodes_and_existing_selection_metadata_are_preserved() -> None:
    """Reordering retains duplicate objects, integration decisions and all pre-existing marks."""
    nodeid = pytest_priorities.PRIORITY_NODEIDS[0]
    marks = (pytest.mark.integration, pytest.mark.xdist_group(name="existing-group"))
    first, second = _Item(nodeid, "first", marks), _Item(nodeid, "second", marks)
    unknown = _Item("tests/test_generated.py::test_case", "unknown", marks)
    items = [unknown, first, second]
    objects = {id(item) for item in items}
    node_counts = Counter(item.nodeid for item in items)
    metadata = {id(item): item.marks for item in items}
    _prioritize(items)
    assert items == [first, second, unknown]
    assert {id(item) for item in items} == objects
    assert Counter(item.nodeid for item in items) == node_counts
    assert {id(item): item.marks for item in items} == metadata


def test_sandbox_group_keeps_every_case_marker_and_relative_order() -> None:
    """Priority hints do not regroup or reorder the separate sandbox workload."""
    marker = pytest.mark.xdist_group(name="custom-sandbox-security")
    security = [
        _Item(
            f"tests/operators/custom_sandbox/test_security.py::test_generated[{index}]",
            marks=(marker,),
        )
        for index in range(29)
    ]
    long_case = _Item(pytest_priorities.PRIORITY_NODEIDS[0])
    items = [*security[:10], long_case, *security[10:]]
    _prioritize(items)
    assert items == [long_case, *security]
    assert all(item.marks == (marker,) for item in security)


def test_stale_hints_never_remove_unlisted_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """A renamed hinted test cannot cause selection loss when old hint data remains."""
    monkeypatch.setattr(pytest_priorities, "PRIORITY_NODEIDS", ("tests/deleted.py::test_removed",))
    items = [_Item("tests/test_generated.py::test_new"), _Item("tests/test_other.py::test_old")]
    original = tuple(items)
    _prioritize(items)
    assert tuple(items) == original
