# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate fictional customer, store, and booked-sales metadata."""

from datakeel.sample_enterprise.common import CATEGORIES, CHANNELS, REGIONS, day, table
from datakeel.sample_enterprise.models import SourceData, ViewData


def build_crm() -> SourceData:
    """Produce five CRM tables with a booked-sales view."""
    regions = table(
        "regions",
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL",
        tuple((i + 1, name) for i, name in enumerate(REGIONS)),
    )
    customers = table(
        "customers",
        "id INTEGER PRIMARY KEY, name TEXT, region TEXT, joined_date TEXT, customer_type TEXT",
        tuple(
            (i, f"样例客户{i:04}", REGIONS[i % 4], day(i), "个人" if i % 3 else "企业")
            for i in range(1, 1201)
        ),
    )
    stores = table(
        "stores",
        "id INTEGER PRIMARY KEY, name TEXT, region_id INTEGER REFERENCES regions(id)",
        tuple((i, f"虚构门店{i:03}", i % 4 + 1) for i in range(1, 161)),
    )
    campaigns = table(
        "campaigns",
        "id INTEGER PRIMARY KEY, name TEXT, budget INTEGER",
        tuple((i, f"样例活动{i:02}", i * 1000) for i in range(1, 25)),
    )
    sales = table(
        "sales",
        "id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), "
        "store_id INTEGER REFERENCES stores(id), date TEXT, region TEXT, channel TEXT, "
        "category TEXT, quantity INTEGER, invoiced_amount INTEGER, status TEXT",
        tuple(
            (
                i,
                i % 1200 + 1,
                i % 160 + 1,
                day(i * 2),
                REGIONS[i % 4],
                CHANNELS[i % 3],
                CATEGORIES[i % 4],
                i % 5 + 1,
                (i % 5 + 1) * (650 + i % 80 * 30),
                "draft" if i % 13 == 0 else "booked",
            )
            for i in range(1, 8001)
        ),
    )
    return SourceData(
        id="crm",
        name="Fictional Kitchen Co. CRM",
        tables=(regions, customers, stores, campaigns, sales),
        views=(
            ViewData(
                name="sales_summary",
                query="SELECT id, customer_id, date, region, channel, category, quantity, "
                "invoiced_amount "
                "FROM sales WHERE status = 'booked'",
            ),
        ),
    )
