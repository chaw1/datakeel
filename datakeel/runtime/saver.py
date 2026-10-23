# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Synchronous graph checkpoint adapter backed by the existing fact store."""

from collections.abc import AsyncIterator, Collection, Iterator, Sequence
from typing import NoReturn, Self, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

from datakeel.runtime.serializer import PrimitiveSerializer
from datakeel.storage import checkpoint_store as store
from datakeel.storage.database import Database

_ASYNC = "Datakeel runtime uses synchronous checkpoint APIs; async is unsupported"


def _config(key: store.CheckpointKey) -> RunnableConfig:
    return {"configurable": key.model_dump()}


class SQLAlchemySaver(BaseCheckpointSaver[int]):
    """Translate framework checkpoints to typed, opaque storage transactions."""

    def __init__(self, db: Database) -> None:
        """Bind one fact store and a non-extensible primitive serializer."""
        super().__init__(serde=PrimitiveSerializer())
        self.db = db

    def with_allowlist(self, extra_allowlist: Collection[tuple[str, ...]]) -> Self:
        """Keep the fixed codec even when graph compilation suggests additional classes."""
        del extra_allowlist
        return self

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Commit a complete snapshot without copying ephemeral config into metadata."""
        del new_versions
        scope = config.get("configurable", {})
        key = store.CheckpointKey(
            thread_id=scope["thread_id"],
            checkpoint_ns=scope.get("checkpoint_ns", ""),
            checkpoint_id=checkpoint["id"],
        )
        store.put_checkpoint(
            self.db,
            store.CheckpointRecord(
                key=key,
                checkpoint=self.serde.dumps_typed(checkpoint)[1],
                metadata=self.serde.dumps_typed(metadata)[1],
                parent_checkpoint_id=scope.get("checkpoint_id"),
            ),
        )
        return _config(key)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, object]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """Record task results once, updating only negative-index control writes."""
        scope = config.get("configurable", {})
        key = store.CheckpointKey(
            thread_id=scope["thread_id"],
            checkpoint_ns=scope.get("checkpoint_ns", ""),
            checkpoint_id=scope["checkpoint_id"],
        )
        store.put_writes(
            self.db,
            key,
            [
                store.CheckpointWrite(
                    task_id=task_id,
                    task_path=task_path,
                    idx=WRITES_IDX_MAP.get(channel, idx),
                    channel=channel,
                    value=self.serde.dumps_typed(
                        str(value)
                        if channel == "__error__" and isinstance(value, BaseException)
                        else value
                    )[1],
                )
                for idx, (channel, value) in enumerate(writes)
            ],
        )

    def _tuple(self, record: store.CheckpointRecord) -> CheckpointTuple:
        parent = record.key.model_copy(update={"checkpoint_id": record.parent_checkpoint_id})
        return CheckpointTuple(
            config=_config(record.key),
            checkpoint=cast("Checkpoint", self.serde.loads_typed(("json", record.checkpoint))),
            metadata=cast("CheckpointMetadata", self.serde.loads_typed(("json", record.metadata))),
            parent_config=_config(parent) if record.parent_checkpoint_id else None,
            pending_writes=[
                (write.task_id, write.channel, self.serde.loads_typed(("json", write.value)))
                for write in record.writes
            ],
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Read an exact checkpoint or the latest snapshot in the default namespace."""
        scope = config.get("configurable", {})
        scoped: RunnableConfig = {
            "configurable": {
                "thread_id": scope["thread_id"],
                "checkpoint_id": scope.get("checkpoint_id"),
                "checkpoint_ns": scope.get("checkpoint_ns", ""),
            }
        }
        return next(self.list(scoped, limit=1), None)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, object] | None = None,  # noqa: A002  # Framework contract name.
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """Filter decoded metadata before limiting snapshots in descending ID order."""
        self.serde.dumps_typed(filter)
        scope = (config or {}).get("configurable", {})
        query = store.CheckpointQuery(
            thread_id=scope.get("thread_id"),
            checkpoint_ns=scope.get("checkpoint_ns"),
            checkpoint_id=scope.get("checkpoint_id"),
            before=(before or {}).get("configurable", {}).get("checkpoint_id"),
        )
        for record in store.list_checkpoints(self.db, query):
            result = self._tuple(record)
            if filter and any(result.metadata.get(key) != value for key, value in filter.items()):
                continue
            if limit is not None and limit <= 0:
                return
            yield result
            if limit is not None:
                limit -= 1

    def delete_thread(self, thread_id: str) -> None:
        """Remove graph state without deleting transcripts, model traces or budgets."""
        store.delete_thread(self.db, thread_id)

    def get_next_version(self, current: int | None, channel: None) -> int:
        """Increment an integer channel version monotonically."""
        del channel
        return 1 if current is None else current + 1

    async def _async_unavailable(self, *args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        raise NotImplementedError(_ASYNC)

    aget = aget_tuple = aput = aput_writes = adelete_thread = _async_unavailable
    adelete_for_runs = acopy_thread = aprune = aget_delta_channel_history = _async_unavailable

    async def alist(self, *args: object, **kwargs: object) -> AsyncIterator[CheckpointTuple]:
        """Reject asynchronous iteration because the runtime owns synchronous transactions."""
        yield await self._async_unavailable(*args, **kwargs)
