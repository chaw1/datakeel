import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockStandardsFetch, standard } from "./fixtures";
import { StandardEditor } from "./StandardEditor";

it("preserves standard constraints and reviews edits without applying them", async () => {
  const fetch = mockStandardsFetch();
  const user = userEvent.setup();
  render(
    <StandardEditor
      definition={standard}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.clear(screen.getByLabelText("Maximum length"));
  await user.type(screen.getByLabelText("Maximum length"), "10");
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: update_standard",
    }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[1]?.body,
  ).toBe(JSON.stringify({ definition: { ...standard, length: 10 } }));
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});
