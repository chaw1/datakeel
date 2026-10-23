# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate fictional retail transactions, payments, and returns."""

from datakeel.sample_enterprise.common import CATEGORIES, CHANNELS, REGIONS, day, table
from datakeel.sample_enterprise.models import SourceData, TableData, ViewData


def _orders() -> TableData:
    return table(
        "orders",
        "id INTEGER PRIMARY KEY, date TEXT, region TEXT, channel TEXT, category TEXT, "
        "quantity INTEGER, paid_amount INTEGER, list_amount INTEGER, status TEXT",
        tuple(
            (
                i,
                day(i * 5),
                REGIONS[i % 4],
                CHANNELS[i % 3],
                CATEGORIES[i % 4],
                i % 3 + 1,
                (i % 3 + 1) * (699 + i % 80 * 29),
                (i % 3 + 1) * (799 + i % 80 * 29),
                "cancelled" if i % 11 == 0 else "completed",
            )
            for i in range(1, 18001)
        ),
    )


def build_ecommerce() -> SourceData:
    """Produce five ecommerce tables and a paid-retail lineage view."""
    returns = table(
        "returns",
        "id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), "
        "date TEXT, region TEXT, refund_amount INTEGER, status TEXT",
        tuple(
            (
                i,
                i * 19 % 18000 + 1,
                day(i * 11),
                REGIONS[i % 4],
                199 + i % 500,
                "pending" if i % 9 == 0 else "approved",
            )
            for i in range(1, 901)
        ),
    )
    items = table(
        "order_items",
        "id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), "
        "product_code TEXT, quantity INTEGER, amount INTEGER",
        tuple(
            (i, i % 18000 + 1, f"P{i % 80 + 1:03}", i % 3 + 1, 699 + i % 80 * 29)
            for i in range(1, 6001)
        ),
    )
    payments = table(
        "payments",
        "id INTEGER PRIMARY KEY, order_id INTEGER REFERENCES orders(id), "
        "date TEXT, channel TEXT, amount INTEGER, status TEXT",
        tuple(
            (
                i,
                i * 7 % 18000 + 1,
                day(i * 19),
                CHANNELS[i % 3],
                699 + i % 80 * 29,
                "pending" if i % 19 == 0 else "paid",
            )
            for i in range(1, 1801)
        ),
    )
    promotions = table(
        "promotions",
        "id INTEGER PRIMARY KEY, name TEXT, discount_amount INTEGER",
        tuple((i, f"虚构优惠{i:02}", i * 10) for i in range(1, 25)),
    )
    return SourceData(
        id="ecommerce",
        name="Fictional Kitchen Co. Ecommerce",
        tables=(_orders(), returns, items, payments, promotions),
        views=(
            ViewData(
                name="retail_summary",
                query="SELECT id, date, region, channel, category, quantity, paid_amount "
                "FROM orders WHERE status = 'completed'",
            ),
        ),
    )
