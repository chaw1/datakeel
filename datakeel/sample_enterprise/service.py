# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate fictional after-sales tickets, repairs, and warranties."""

from datakeel.sample_enterprise.common import CATEGORIES, REGIONS, day, table
from datakeel.sample_enterprise.models import SourceData, ViewData


def build_service() -> SourceData:
    """Produce five after-sales tables with a ticket projection view."""
    codes = table(
        "failure_codes",
        "id INTEGER PRIMARY KEY, code TEXT, description TEXT",
        tuple((i, f"F{i:03}", f"合成故障描述{i}") for i in range(1, 13)),
    )
    parts = table(
        "parts",
        "id INTEGER PRIMARY KEY, name TEXT, unit_cost INTEGER",
        tuple((i, f"虚构零件{i:02}", 10 + i * 3) for i in range(1, 61)),
    )
    tickets = table(
        "tickets",
        "id INTEGER PRIMARY KEY, date TEXT, region TEXT, category TEXT, "
        "failure_code_id INTEGER REFERENCES failure_codes(id), status TEXT",
        tuple(
            (
                i,
                day(i * 17),
                REGIONS[i % 4],
                CATEGORIES[i % 4],
                i % 12 + 1,
                "open" if i % 5 == 0 else "closed",
            )
            for i in range(1, 1201)
        ),
    )
    repairs = table(
        "repairs",
        "id INTEGER PRIMARY KEY, ticket_id INTEGER REFERENCES tickets(id), "
        "part_id INTEGER REFERENCES parts(id), date TEXT, region TEXT, labor_cost INTEGER",
        tuple(
            (i, i % 1200 + 1, i % 60 + 1, day(i * 17), REGIONS[i % 4], 60 + i % 120)
            for i in range(1, 901)
        ),
    )
    warranties = table(
        "warranties",
        "id INTEGER PRIMARY KEY, product_code TEXT, start_date TEXT, months INTEGER",
        tuple((i, f"P{i % 80 + 1:03}", day(i), 24) for i in range(1, 801)),
    )
    return SourceData(
        id="service",
        name="Fictional Kitchen Co. After-sales",
        tables=(codes, parts, tickets, repairs, warranties),
        views=(
            ViewData(
                name="ticket_summary",
                query=("SELECT id, date, region, category, failure_code_id, status FROM tickets"),
            ),
        ),
    )
