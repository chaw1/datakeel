# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate arbitrary regular expressions so backtracking cannot stall a worker."""

import multiprocessing
import re
from multiprocessing.connection import Connection

from datakeel.core.catalog_models import SourceProperties
from datakeel.core.dq_models import DqMetrics, DqRule
from datakeel.core.errors import ExecutionError
from datakeel.core.models import BoundaryModel
from datakeel.quality.dq_source import iter_rule_values
from datakeel.quality.dq_statistics import ColumnStatistics

_SAMPLE_LIMIT = 5


class RegexObservation(BoundaryModel):
    """Return only constant-size aggregate evidence from the isolated regex scanner."""

    metrics: DqMetrics
    failed_count: int
    samples: tuple[int, ...]


def regex_observation(rule: DqRule, source: SourceProperties) -> RegexObservation:
    """Stream and match in one isolated process under the complete rule deadline."""
    context = multiprocessing.get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    process = context.Process(target=_match_stream, args=(writer, rule, source), daemon=True)
    process.start()
    writer.close()
    try:
        if not reader.poll(rule.timeout_ms / 1000):
            msg = "Quality regex execution exceeded its timeout"
            raise ExecutionError(msg)
        result = reader.recv()
        if isinstance(result, str):
            raise ExecutionError(result)
        return RegexObservation.model_validate(result)
    except EOFError as error:
        msg = "Quality regex execution could not produce a result"
        raise ExecutionError(msg) from error
    finally:
        reader.close()
        if process.is_alive():
            process.terminate()
        process.join()
        process.close()


def _match_stream(writer: Connection, rule: DqRule, source: SourceProperties) -> None:
    compiled = re.compile(rule.params.pattern or "")
    statistics = ColumnStatistics()
    failed = 0
    samples: list[int] = []
    try:
        for values in iter_rule_values(rule, source):
            for index, value in enumerate(values, statistics.rows + 1):
                if value is not None and compiled.fullmatch(str(value)) is None:
                    failed += 1
                    if len(samples) < _SAMPLE_LIMIT:
                        samples.append(index)
            statistics.add(values)
        writer.send(
            RegexObservation(
                metrics=statistics.metrics(), failed_count=failed, samples=tuple(samples)
            ).model_dump()
        )
    except ExecutionError as error:
        writer.send(str(error))
    finally:
        writer.close()
