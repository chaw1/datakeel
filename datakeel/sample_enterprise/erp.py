# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate the fictional product, shipping, and inventory source."""

from datakeel.sample_enterprise.common import CATEGORIES, CHANNELS, REGIONS, day, table
from datakeel.sample_enterprise.models import SourceData, ViewData


def build_erp() -> SourceData:
    """Produce five ERP tables and a transparent shipping projection."""
    products = table(
        "products",
        "id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, unit_price INTEGER",
        tuple((i, f"虚构厨电产品{i:03}", CATEGORIES[i % 4], 500 + i * 25) for i in range(1, 81)),
    )
    warehouses = table(
        "warehouses",
        "id INTEGER PRIMARY KEY, name TEXT, region TEXT",
        tuple((i, f"样例仓库{i}", REGIONS[i % 4]) for i in range(1, 9)),
    )
    suppliers = table(
        "suppliers",
        "id INTEGER PRIMARY KEY, name TEXT, region TEXT",
        tuple((i, f"虚构供应商{i:02}", REGIONS[i % 4]) for i in range(1, 21)),
    )
    shipments = table(
        "shipments",
        "id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), date TEXT NOT NULL, "
        "region TEXT, channel TEXT, category TEXT, quantity INTEGER, shipped_amount INTEGER, "
        "status TEXT",
        tuple(
            (
                i,
                i % 80 + 1,
                day(i),
                REGIONS[i % 4],
                CHANNELS[i % 3],
                CATEGORIES[i % 4],
                i % 7 + 1,
                (i % 7 + 1) * (525 + i % 80 * 25),
                "cancelled" if i % 17 == 0 else "shipped",
            )
            for i in range(1, 12001)
        ),
    )
    inventory = table(
        "inventory",
        "id INTEGER PRIMARY KEY, product_id INTEGER REFERENCES products(id), "
        "warehouse_id INTEGER REFERENCES warehouses(id), date TEXT, quantity INTEGER, region TEXT",
        tuple(
            (i, i % 80 + 1, i % 8 + 1, "2026-09-30", i % 40 + 5, REGIONS[i % 4])
            for i in range(1, 801)
        ),
    )
    return SourceData(
        id="erp",
        name="Fictional Kitchen Co. ERP",
        tables=(products, warehouses, suppliers, shipments, inventory),
        views=(
            ViewData(
                name="shipment_summary",
                query="SELECT id, product_id, date, region, channel, category, quantity, "
                "shipped_amount "
                "FROM shipments WHERE status = 'shipped'",
            ),
        ),
    )
