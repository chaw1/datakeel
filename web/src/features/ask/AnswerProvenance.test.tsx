import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AnswerProvenance } from "./AnswerProvenance";
import { retailAnswer, unavailableAnswer } from "./testFixtures";

it("starts with collapsed SQL and opens catalog lineage for the registered metric", async () => {
  const user = userEvent.setup();
  const onOpenReceipt = vi.fn();
  render(
    <AnswerProvenance answer={retailAnswer} onOpenReceipt={onOpenReceipt} />,
  );
  const sql = screen.getByText(
    "SELECT SUM(amount) AS value FROM orders WHERE region = :region",
  );
  expect(sql).not.toBeVisible();
  await user.click(screen.getByText("SQL and bound parameters"));
  expect(sql).toBeVisible();
  expect(screen.getByText(/"region": "华东"/)).toBeVisible();
  await user.click(screen.getByText("Source tables and fields"));
  expect(screen.getByText("ecommerce/main/orders")).toBeVisible();
  expect(screen.getByText("ecommerce/main/orders/amount")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "View lineage" }));
  expect(onOpenReceipt).toHaveBeenCalledWith({
    assetId: "retail_revenue",
    includeCatalog: true,
  });
});

it("omits SQL and lineage when no metric was resolved", () => {
  render(
    <AnswerProvenance answer={unavailableAnswer} onOpenReceipt={vi.fn()} />,
  );
  expect(
    screen.queryByText("SQL and bound parameters"),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "View lineage" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(unavailableAnswer.question)).toBeVisible();
});
