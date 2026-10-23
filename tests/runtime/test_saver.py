# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One synchronous checkpoint contract exercised by both database test matrices."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, TypedDict

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Interrupt, interrupt

from datakeel.core.errors import ValidationError
from datakeel.core.models import new_id
from datakeel.runtime.saver import SQLAlchemySaver
from datakeel.runtime.serializer import PrimitiveSerializer

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata

    from datakeel.storage.database import Database


def _config(thread: str = "thread", namespace: str = "") -> RunnableConfig:
    return {"configurable": {"thread_id": thread, "checkpoint_ns": namespace}}


def _checkpoint(checkpoint_id: str) -> Checkpoint:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["channel_values"] = {"text": "before\x00after", "count": 1}
    checkpoint["channel_versions"] = {"text": 1, "count": 1}
    return checkpoint


def _put(
    saver: SQLAlchemySaver,
    checkpoint_id: str,
    config: RunnableConfig | None = None,
    metadata: CheckpointMetadata | None = None,
) -> RunnableConfig:
    return saver.put(
        config or _config(),
        _checkpoint(checkpoint_id),
        metadata or {"source": "loop", "step": 1, "parents": {}},
        {"text": 1, "count": 1},
    )


def test_checkpoint_when_reloaded_preserves_snapshot_parent_and_namespace(db: Database) -> None:
    """Round-trip complete channel state and isolate identical IDs in separate namespaces."""
    saver = SQLAlchemySaver(db)
    assert saver.get_tuple(_config()) is None
    first = _put(saver, "001")
    second = _put(saver, "002", first)
    other_namespace = _put(saver, "002", _config(namespace="other"))
    other_thread = _put(saver, "002", _config(thread="other"))
    fresh = SQLAlchemySaver(db)
    latest = fresh.get_tuple(_config())
    assert latest is not None
    assert latest.config == second
    assert latest.parent_config == first
    assert latest.checkpoint["channel_values"] == {"text": "before\x00after", "count": 1}
    assert latest.checkpoint["channel_versions"] == {"text": 1, "count": 1}
    assert fresh.get(first) == _checkpoint("001") | {"ts": fresh.get(first)["ts"]}
    assert fresh.get_tuple(other_namespace).parent_config is None
    assert fresh.get_tuple(other_thread).parent_config is None
    assert fresh.get_tuple({"configurable": {"thread_id": "thread"}}) == latest
    assert fresh.config_specs == []
    with pytest.raises(KeyError, match="thread_id"):
        fresh.get_tuple({"configurable": {}})


def test_checkpoint_when_same_key_replaced_keeps_one_current_snapshot(db: Database) -> None:
    """An interrupted retry updates one checkpoint instead of creating duplicate rows."""
    saver = SQLAlchemySaver(db)
    _put(saver, "001")
    updated = _checkpoint("001")
    updated["channel_values"] = {"replaced": True}
    saver.put(_config(), updated, {"source": "update", "step": 2}, {})
    records = list(saver.list(_config()))
    assert len(records) == 1
    assert records[0].checkpoint == updated
    assert records[0].metadata == {"source": "update", "step": 2}


def test_listing_when_filtered_applies_before_and_limit_after_metadata_matching(
    db: Database,
) -> None:
    """Pagination remains correct when the newest checkpoint does not match the filter."""
    saver = SQLAlchemySaver(db)
    first = _put(saver, "001", metadata={"source": "input", "step": 1})
    middle = _put(saver, "002", metadata={"source": "loop", "step": 2})
    _put(saver, "003", metadata={"source": "input", "step": 3})
    _put(saver, "004", _config(namespace="other"))
    assert [item.checkpoint["id"] for item in saver.list(_config())] == ["003", "002", "001"]
    assert [item.config for item in saver.list(_config(), filter={"source": "loop"}, limit=1)] == [
        middle
    ]
    assert [item.config for item in saver.list(_config(), before=middle)] == [first]
    assert [item.config for item in saver.list(first)] == [first]
    assert len(list(saver.list({"configurable": {"thread_id": "thread"}}))) == 4
    assert len(list(saver.list(None))) == 4
    assert list(saver.list(None, limit=0)) == []
    assert list(saver.list(None, limit=-1)) == []
    assert list(saver.list(None, filter={"step": 99}, limit=1)) == []
    with pytest.raises(ValidationError, match="allowlist"):
        list(saver.list(None, filter={"unsafe": object()}))


def test_writes_when_retried_keep_ordinary_values_and_replace_special_indices(db: Database) -> None:
    """Control writes upsert without overwriting completed ordinary task results."""
    saver = SQLAlchemySaver(db)
    config = _put(saver, "001")
    saver.put_writes(config, [("value", "first"), ("second", 2)], "task", "original")
    saver.put_writes(config, [("changed", "later"), ("second", 999)], "task", "later")
    saver.put_writes(config, [("__error__", "old"), ("__resume__", [1])], "task")
    saver.put_writes(config, [("__error__", ValueError("new")), ("__resume__", [2])], "task")
    assert SQLAlchemySaver(db).get_tuple(config).pending_writes == [
        ("task", "__resume__", [2]),
        ("task", "__error__", "new"),
        ("task", "value", "first"),
        ("task", "second", 2),
    ]


def test_writes_when_task_ids_disagree_with_paths_return_execution_order(db: Database) -> None:
    """Sort pending writes by task path, then task ID, then numeric write index."""
    saver = SQLAlchemySaver(db)
    config = _put(saver, "001")
    saver.put_writes(config, [("v", "late")], "a", "z")
    saver.put_writes(config, [("v", "early-0"), ("v", "early-1")], "z", "a")
    saver.put_writes(config, [("v", "first")], "b", "a")
    assert saver.get_tuple(config).pending_writes == [
        ("b", "v", "first"),
        ("z", "v", "early-0"),
        ("z", "v", "early-1"),
        ("a", "v", "late"),
    ]


def test_writes_when_concurrent_keep_one_ordinary_result(db: Database) -> None:
    """Dialect conflict handling serializes competing inserts under the common write lock."""
    saver = SQLAlchemySaver(db)
    config = _put(saver, "001")
    saver.put_writes(config, [("v", "committed")], "task")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: saver.put_writes(config, [("v", "retry")], "task"), range(8)))
    assert saver.get_tuple(config).pending_writes == [("task", "v", "committed")]


def test_checkpoint_when_metadata_is_unregistered_rejects_before_persistence(db: Database) -> None:
    """Untrusted metadata and writes cannot leave partially serialized database state."""
    saver = SQLAlchemySaver(db)
    with pytest.raises(ValidationError, match="allowlist"):
        _put(saver, "001", metadata={"unsafe": object()})
    assert saver.get_tuple(_config()) is None
    config = _put(saver, "001")
    with pytest.raises(ValidationError, match="allowlist"):
        saver.put_writes(config, [("valid", "value"), ("unsafe", object())], "task")
    assert saver.get_tuple(config).pending_writes == []


def test_metadata_when_config_contains_ephemeral_values_does_not_copy_them(db: Database) -> None:
    """Only explicitly supplied checkpoint metadata is persisted."""
    saver = SQLAlchemySaver(db)
    config = _config()
    config["configurable"]["response_token"] = new_id()
    config["metadata"] = {"response_token": new_id()}
    result = saver.get_tuple(_put(saver, "001", config))
    assert result.metadata == {"source": "loop", "step": 1, "parents": {}}
    assert "response_token" not in result.config["configurable"]
    assert saver.get_next_version(None, None) == 1
    assert saver.get_next_version(99, None) == 100
    assert saver.with_allowlist({("arbitrary", "Object")}) is saver
    saver.delete_thread("thread")
    assert saver.get_tuple(_config()) is None


class _State(TypedDict):
    plan_id: str
    completed: bool


def test_interrupt_when_saver_recreated_resumes_without_repeating_completed_node(
    db: Database,
) -> None:
    """Persist real graph interrupt writes and reconstruct them across saver instances."""
    calls: list[str] = []

    def prepare(state: _State) -> _State:
        calls.append("prepare")
        return state

    def approval_gate(state: _State) -> dict[str, object]:
        interrupt({"plan_id": state["plan_id"]})
        return {}

    graph = StateGraph(_State)
    graph.add_node("prepare", prepare)
    graph.add_node("approval_gate", approval_gate)
    graph.add_node("complete", lambda _: {"completed": True})
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "approval_gate")
    graph.add_edge("approval_gate", "complete")
    graph.add_edge("complete", END)
    first = graph.compile(checkpointer=SQLAlchemySaver(db))
    paused = first.invoke({"plan_id": "plan", "completed": False}, _config(), durability="sync")
    pause = paused["__interrupt__"][0]
    assert pause.value == {"plan_id": "plan"}
    restarted = graph.compile(checkpointer=SQLAlchemySaver(db))
    assert restarted.get_state(_config()).interrupts == (pause,)
    result = restarted.invoke(Command(resume={pause.id: True}), _config(), durability="sync")
    assert result == {"plan_id": "plan", "completed": True}
    assert calls == ["prepare"]


def test_failed_node_when_checkpointing_preserves_original_error_as_text(db: Database) -> None:
    """Framework error bookkeeping never attempts to deserialize arbitrary exception classes."""

    def fail(_state: _State) -> _State:
        msg = "controlled failure"
        raise ValueError(msg)

    graph = StateGraph(_State)
    graph.add_node("fail", fail)
    graph.add_edge(START, "fail")
    graph.add_edge("fail", END)
    saver = SQLAlchemySaver(db)
    with pytest.raises(ValueError, match="controlled failure"):
        graph.compile(checkpointer=saver).invoke(
            {"plan_id": "plan", "completed": False},
            _config(),
            durability="sync",
        )
    assert [
        (channel, value) for _, channel, value in saver.get_tuple(_config()).pending_writes
    ] == [
        ("__error__", "controlled failure"),
    ]


@pytest.mark.parametrize(
    "method",
    [
        "aget",
        "aget_tuple",
        "aput",
        "aput_writes",
        "adelete_thread",
        "adelete_for_runs",
        "acopy_thread",
        "aprune",
        "aget_delta_channel_history",
    ],
)
def test_async_methods_when_called_explain_synchronous_runtime(db: Database, method: str) -> None:
    """Never fall back to blocking database work inside an asynchronous interface."""
    with pytest.raises(NotImplementedError, match="synchronous checkpoint APIs"):
        asyncio.run(getattr(SQLAlchemySaver(db), method)(_config()))


def test_async_listing_when_iterated_explains_synchronous_runtime(db: Database) -> None:
    """Expose an async iterator that fails with the same explicit unsupported reason."""
    with pytest.raises(NotImplementedError, match="synchronous checkpoint APIs"):
        asyncio.run(anext(SQLAlchemySaver(db).alist(None)))


def test_serializer_when_primitive_envelopes_round_trip_preserves_types() -> None:
    """Tuple, bytes and fixed interrupt envelopes retain their exact supported shapes."""
    serializer = PrimitiveSerializer()
    value = {
        "values": [None, True, 2, 1.5, "\x00好", b"\x00\xff", (1, "two")],
        "pause": Interrupt({"plan_id": "plan"}, id="pause"),
    }
    assert serializer.loads_typed(serializer.dumps_typed(value)) == value
    constructor = {"lc": 2, "type": "constructor", "id": ["pathlib", "Path"]}
    assert serializer.loads_typed(serializer.dumps_typed(constructor)) == constructor


@pytest.mark.parametrize(
    "value",
    [
        object(),
        ValueError("unsafe"),
        {1: "key"},
        {"unsafe": object()},
        Interrupt("value", response_schema=str),
        float("nan"),
    ],
)
def test_serializer_when_unregistered_value_rejects_encoding(value: object) -> None:
    """No arbitrary object or schema class becomes a persisted constructor."""
    with pytest.raises(ValueError, match=r"allowlist|Out of range float values"):
        PrimitiveSerializer().dumps_typed(value)


@pytest.mark.parametrize(
    "data",
    [
        ("pickle", b"payload"),
        ("json", b'{"lc":2,"type":"constructor"}'),
        ("json", b'["constructor",["pathlib","Path"]]'),
        ("json", b'["list",{}]'),
        ("json", b'["interrupt",[42,{}]]'),
        ("json", b"[]"),
    ],
)
def test_serializer_when_unknown_envelope_rejects_decoding(data: tuple[str, bytes]) -> None:
    """Reject unknown tags and malformed envelopes without resolving class names."""
    with pytest.raises(ValidationError, match="allowlist"):
        PrimitiveSerializer().loads_typed(data)
