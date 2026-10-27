# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate arbitrary regular expressions so backtracking cannot stall a worker."""

import multiprocessing
import re
from multiprocessing.connection import Connection
from typing import cast

from datakeel.core.errors import ExecutionError
from datakeel.core.metric_models import Scalar


def regex_violations(pattern: str, values: tuple[Scalar, ...], timeout_ms: int) -> tuple[int, ...]:
    """Evaluate cells in one private process and terminate only that process on timeout."""
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_match_rows, args=(writer, pattern, values), daemon=True)
    process.start()
    writer.close()
    try:
        if not reader.poll(timeout_ms / 1000):
            msg = "Quality regex execution exceeded its timeout"
            raise ExecutionError(msg)
        return cast("tuple[int, ...]", reader.recv())
    except EOFError as error:
        msg = "Quality regex execution could not produce a result"
        raise ExecutionError(msg) from error
    finally:
        reader.close()
        if process.is_alive():
            process.terminate()
        process.join()
        process.close()


def _match_rows(writer: Connection, pattern: str, values: tuple[Scalar, ...]) -> None:
    compiled = re.compile(pattern)
    try:
        writer.send(
            tuple(
                index
                for index, value in enumerate(values, 1)
                if value is not None and compiled.fullmatch(str(value)) is None
            )
        )
    finally:
        writer.close()
