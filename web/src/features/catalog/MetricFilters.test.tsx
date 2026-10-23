import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { metric } from "./fixtures";
import { MetricFilters } from "./MetricFilters";

it("keeps inclusion-list values typed and supports removing a condition", async () => {
  const changed = vi.fn();
  const user = userEvent.setup();
  render(
    <MetricFilters
      filters={metric.definition.filters ?? []}
      table={metric.definition.measure.table}
      onChange={changed}
    />,
  );
  await user.selectOptions(screen.getByLabelText("Comparison"), "in");
  expect(changed).toHaveBeenCalledWith([
    { column: "ecommerce/main/orders/status", op: "in", value: ["completed"] },
  ]);
  await user.click(screen.getByRole("button", { name: "Remove condition" }));
  expect(changed).toHaveBeenLastCalledWith([]);
});
