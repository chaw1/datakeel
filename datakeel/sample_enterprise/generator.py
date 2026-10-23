# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Materialize small, byte-reproducible fictional SQLite sources and benchmark gold."""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile

from datakeel.sample_enterprise.crm import build_crm
from datakeel.sample_enterprise.ecommerce import build_ecommerce
from datakeel.sample_enterprise.erp import build_erp
from datakeel.sample_enterprise.gold import calculate_gold
from datakeel.sample_enterprise.models import EnterpriseSample, SourceData, SourceSample
from datakeel.sample_enterprise.service import build_service


def _materialize(source: SourceData, path: Path) -> SourceSample:
    with NamedTemporaryFile(dir=path.parent, suffix=".sqlite", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with closing(sqlite3.connect(temporary_path)) as database, database:
            database.execute("PRAGMA foreign_keys = ON")
            for table in source.tables:
                database.execute(f'CREATE TABLE "{table.name}" ({table.definition})')
                placeholders = ", ".join("?" for _ in table.columns)
                # Identifiers are authored constants; all generated values use bound parameters.
                insert = f'INSERT INTO "{table.name}" VALUES ({placeholders})'  # noqa: S608
                database.executemany(insert, table.rows)
            for view in source.views:
                database.execute(f'CREATE VIEW "{view.name}" AS {view.query}')
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return SourceSample(
        id=source.id,
        name=source.name,
        path=path,
        row_count=sum(len(table.rows) for table in source.tables),
        table_count=len(source.tables),
        view_count=len(source.views),
    )


def generate_enterprise(output_dir: Path) -> EnterpriseSample:
    """Generate four SQLite files and gold.json in a caller-owned local directory.

    Existing generated filenames are replaced atomically. Data depends only on
    fixed arithmetic and the reference date, with no network or random seed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = (build_erp(), build_crm(), build_ecommerce(), build_service())
    generated = tuple(
        _materialize(source, output_dir / f"{source.id}.sqlite") for source in sources
    )
    gold_path = output_dir / "gold.json"
    gold_path.write_text(calculate_gold(sources).model_dump_json(indent=2) + "\n", encoding="utf-8")
    return EnterpriseSample(sources=generated, gold_path=gold_path)
