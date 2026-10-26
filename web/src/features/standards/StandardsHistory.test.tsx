import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockStandardsFetch } from "./fixtures";
import { StandardsHistory } from "./StandardsHistory";

it("restores an immutable revision only through a reviewed controlled action", async () => {
  const fetch = mockStandardsFetch();
  const user = userEvent.setup();
  render(<StandardsHistory onChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(await screen.findByText("Revision 2")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Review restore" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: rollback_standards",
    }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[1]?.body,
  ).toBe(JSON.stringify({ revision: 1 }));
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});
