# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Calculate independent benchmark answers from rows without semantic YAML or SQL."""

from datakeel.core.models import BoundaryModel
from datakeel.sample_enterprise.models import Cell, EnterpriseGold, SourceData, TableData


class GoldRecipe(BoundaryModel):
    """Specify independently reviewed benchmark arithmetic over generated rows."""

    id: str
    table: str
    amount: str | None = None
    equals: tuple[tuple[str, Cell], ...] = ()
    start: str | None = None
    end: str | None = None


_RECIPES = (
    GoldRecipe(
        id="ok-east-retail-last-quarter",
        table="ecommerce/orders",
        amount="paid_amount",
        equals=(("status", "completed"), ("region", "华东")),
        start="2026-07-01",
        end="2026-10-01",
    ),
    GoldRecipe(
        id="ok-retail-march-synonym",
        table="ecommerce/orders",
        amount="paid_amount",
        equals=(("status", "completed"),),
        start="2026-03-01",
        end="2026-04-01",
    ),
    GoldRecipe(
        id="ok-east-shipments-last-quarter",
        table="erp/shipments",
        amount="shipped_amount",
        equals=(("status", "shipped"), ("region", "华东")),
        start="2026-07-01",
        end="2026-10-01",
    ),
    GoldRecipe(
        id="ok-east-sales-last-quarter",
        table="crm/sales",
        amount="invoiced_amount",
        equals=(("status", "booked"), ("region", "华东")),
        start="2026-07-01",
        end="2026-10-01",
    ),
    GoldRecipe(
        id="ok-orders-march",
        table="ecommerce/orders",
        equals=(("status", "completed"),),
        start="2026-03-01",
        end="2026-04-01",
    ),
    GoldRecipe(
        id="ok-refunds-march",
        table="ecommerce/returns",
        amount="refund_amount",
        equals=(("status", "approved"),),
        start="2026-03-01",
        end="2026-04-01",
    ),
    GoldRecipe(
        id="ok-east-inventory",
        table="erp/inventory",
        amount="quantity",
        equals=(("region", "华东"),),
    ),
    GoldRecipe(id="ok-east-customers", table="crm/customers", equals=(("region", "华东"),)),
    GoldRecipe(
        id="ok-east-tickets-last-quarter",
        table="service/tickets",
        equals=(("region", "华东"),),
        start="2026-07-01",
        end="2026-10-01",
    ),
    GoldRecipe(
        id="ok-repairs-march",
        table="service/repairs",
        amount="labor_cost",
        start="2026-03-01",
        end="2026-04-01",
    ),
    GoldRecipe(
        id="ok-online-payments-march",
        table="ecommerce/payments",
        amount="amount",
        equals=(("status", "paid"), ("channel", "线上")),
        start="2026-03-01",
        end="2026-04-01",
    ),
    GoldRecipe(
        id="ok-south-sales-units-last-quarter",
        table="crm/sales",
        amount="quantity",
        equals=(("status", "booked"), ("region", "华南")),
        start="2026-07-01",
        end="2026-10-01",
    ),
    GoldRecipe(
        id="ok-tickets-last-30-days", table="service/tickets", start="2026-09-01", end="2026-10-01"
    ),
    GoldRecipe(
        id="ok-online-retail-last-quarter",
        table="ecommerce/orders",
        amount="paid_amount",
        equals=(("status", "completed"), ("channel", "线上")),
        start="2026-07-01",
        end="2026-10-01",
    ),
)


def _accept(row: dict[str, Cell], recipe: GoldRecipe) -> bool:
    if any(row[column] != value for column, value in recipe.equals):
        return False
    date_value = str(row.get("date", ""))
    return not (
        (recipe.start is not None and date_value < recipe.start)
        or (recipe.end is not None and date_value >= recipe.end)
    )


def _calculate(table: TableData, recipe: GoldRecipe) -> float:
    total = 0.0
    for values in table.rows:
        row = dict(zip(table.columns, values, strict=True))
        if not _accept(row, recipe):
            continue
        if recipe.amount is None:
            total += 1
        else:
            amount = row[recipe.amount]
            if isinstance(amount, (int, float)):
                total += amount
    return total


def calculate_gold(sources: tuple[SourceData, ...]) -> EnterpriseGold:
    """Sum generated Python values using rules independent of the query implementation."""
    tables = {f"{source.id}/{table.name}": table for source in sources for table in source.tables}
    return EnterpriseGold(
        answers={rule.id: _calculate(tables[rule.table], rule) for rule in _RECIPES}
    )
