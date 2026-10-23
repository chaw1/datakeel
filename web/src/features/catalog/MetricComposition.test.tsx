import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { metric, mockCatalogFetch } from "./fixtures";
import { MetricEditor } from "./MetricEditor";

it("does not submit a metric change while composing in any form field", async () => {
  const fetch = mockCatalogFetch();
  const user = userEvent.setup();
  render(
    <MetricEditor card={metric} onChanged={vi.fn()} onOpenReceipt={vi.fn()} />,
  );
  const field = screen.getByLabelText("Metric name");
  const button = screen.getByRole("button", { name: "Review change" });
  const form = field.closest("form");
  if (!form) throw new Error("Metric form missing");
  fireEvent.compositionStart(field);
  fireEvent.submit(form);
  await user.click(button);
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/prepare"))).toBe(
    false,
  );
  fireEvent.compositionEnd(field);
  expect(fireEvent.keyDown(field, { key: "Enter", isComposing: true })).toBe(
    false,
  );
  expect(fireEvent.keyDown(button, { key: "Enter", keyCode: 229 })).toBe(false);
  expect(fireEvent.keyDown(field, { key: "a", isComposing: true })).toBe(true);
  await user.click(button);
  expect(
    await screen.findByRole("article", { name: "Action plan: update_metric" }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/prepare")),
  ).toHaveLength(1);
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});
