# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Small deterministic helpers shared by fictional source builders."""

from datetime import date, timedelta

from datakeel.sample_enterprise.models import Cell, TableData

REGIONS = ("华东", "华南", "华北", "西部")
CHANNELS = ("线上", "门店", "经销商")
CATEGORIES = ("油烟机", "洗碗机", "燃气灶", "蒸烤箱")


def day(index: int) -> str:
    """Distribute synthetic business dates over January through September 2026."""
    return (date(2026, 1, 1) + timedelta(days=index % 273)).isoformat()


def table(name: str, definition: str, rows: tuple[tuple[Cell, ...], ...]) -> TableData:
    """Build an immutable table using columns preceding foreign-key clauses."""
    columns = tuple(
        clause.strip().split()[0]
        for clause in definition.split(",")
        if not clause.strip().startswith("FOREIGN KEY")
    )
    return TableData(name=name, definition=definition, columns=columns, rows=rows)
