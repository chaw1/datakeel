# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Import generated tiny files and measure bounded dataset reads and version comparison."""

from time import perf_counter
from typing import TYPE_CHECKING

from datakeel.core.file_queries import FileQuery
from datakeel.core.models import FileItem
from datakeel.core.search_models import SearchQuery
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.dataset_service import get_dataset, import_paths, list_files
from datakeel.storage.search import search_objects
from datakeel.storage.version_diff import compare_versions
from scripts.scale_bench.common import check_resources, check_space, fingerprint, measure
from scripts.scale_bench.models import Context, Latency, ScenarioResult
from scripts.scale_bench.versions import generate

if TYPE_CHECKING:
    from pathlib import Path


def seed_dataset(context: Context, count: int | None = None) -> str:
    """Seed deterministic metadata only, for query workloads and the L extreme."""
    count = context.scale.files if count is None else count
    check_resources(context, reserve_bytes=count * 2500)
    seed = context.config.seed
    identifier = f"dataset-{seed}"
    files = [
        FileItem(
            id=f"file-{seed}-{index:09d}",
            path="",
            filename=f"file-{index:09d}.txt",
            size=16,
            modality="text",
            sha256=f"{index % 97:064x}",
            metadata={"group": index % 17},
        ).model_dump(mode="json")
        for index in range(count)
    ]
    with context.db.session() as session:
        session.add(
            DatasetRow(id=identifier, name="Generated capacity dataset", files=files, created_at=1)
        )
        session.flush()
        session.add(
            VersionRow(id=f"version-{seed}-0", dataset_id=identifier, manifest=files, created_at=1)
        )
        session.commit()
    return identifier


def _import(context: Context) -> str:
    if context.config.size == "L":
        return seed_dataset(context)
    check_resources(context, reserve_bytes=context.scale.files * 7000)
    directory = context.root / "input"
    directory.mkdir()
    paths: list[Path] = []
    for index in range(context.scale.files):
        if index % 1000 == 0:
            check_space(context.root)
        path = directory / f"file-{index:09d}.txt"
        path.write_text(f"seed={context.config.seed}; group={index % 97}\n")
        paths.append(path)
    return import_paths(context.db, "Generated capacity dataset", paths).id


def _checked_list(context: Context, identifier: str, query: FileQuery) -> None:
    values = list_files(context.db, identifier, query=query)
    expected = min(query.limit or context.scale.files, context.scale.files - query.offset)
    names = [f"file-{index:09d}.txt" for index in range(query.offset, query.offset + expected)]
    if [item.filename for item in values] != names:
        message = "File page lost its generated ordinal or returned incorrect content"
        raise AssertionError(message)


def _checked_search(context: Context) -> None:
    values = search_objects(context.db, SearchQuery(q="file-000", limit=20))
    if [item.name for item in values] != [f"file-{index:09d}.txt" for index in range(20)]:
        message = "Search did not return its expected generated file identities"
        raise AssertionError(message)


def _read_latencies(context: Context, identifier: str) -> dict[str, Latency]:
    repeated = context.config.repeats
    queries = {
        "list": FileQuery(limit=50, offset=context.scale.files // 2),
        "list_first": FileQuery(limit=50),
        "filter": FileQuery(limit=50, q="0000", modality="text"),
    }
    result = {
        name: measure(lambda query=query: _checked_list(context, identifier, query), repeated)
        for name, query in queries.items()
    }
    result["search"] = measure(lambda: _checked_search(context), repeated)
    result["object"] = measure(lambda: get_dataset(context.db, identifier), repeated)
    return result


def run(context: Context) -> ScenarioResult:
    """Measure actual import, pagination, filtered discovery, snapshots and merge comparison."""
    started = perf_counter()
    identifier = _import(context)
    import_seconds = perf_counter() - started
    check_resources(context)
    started = perf_counter()
    snapshot = generate(context, identifier)
    version_seconds = perf_counter() - started
    started = perf_counter()
    diff = compare_versions(context.db, identifier, snapshot.before, snapshot.after, (0, 50))
    diff_seconds = perf_counter() - started
    if (
        diff.counts.unchanged != snapshot.files
        or diff.counts.removed != context.scale.files - snapshot.files
    ):
        message = "Version comparison lost generated file identities"
        raise AssertionError(message)
    reads = _read_latencies(context, identifier)
    return ScenarioResult(
        scenario="B1",
        counts={"files": context.scale.files, "snapshot_files": snapshot.files},
        metrics={
            "import_seconds": import_seconds,
            "snapshot_seconds": version_seconds,
            "version_prepare_seconds": snapshot.prepare_seconds,
            "version_execute_seconds": snapshot.execute_seconds,
            "full_selection_rejected": snapshot.full_selection_rejected,
            "selection_rejection_seconds": snapshot.rejection_seconds,
            "compare_seconds": diff_seconds,
        },
        latencies=reads,
        fixture_sha256=fingerprint(
            {"seed": context.config.seed, "files": context.scale.files, "generator": "tiny-text-v1"}
        ),
        notes=(
            "S/M import real tiny local files; L imports metadata only.",
            "S/M measure real controlled selected-version prepare/execute (at most 10,000 files).",
            "The existing 10,000 selection ceiling rejects a full M/L version request.",
            "L snapshot measures metadata persistence only, without changing the public limit.",
            "Product-generated UUIDs and temporary paths are excluded from fixture identity.",
        ),
    )
