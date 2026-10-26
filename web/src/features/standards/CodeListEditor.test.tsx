import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { CodeListEditor } from "./CodeListEditor";
import { mockStandardsFetch } from "./fixtures";

it("creates typed reference values and submits the complete list for approval", async () => {
  const fetch = mockStandardsFetch();
  const user = userEvent.setup();
  render(
    <CodeListEditor
      definition={{
        code: "",
        name: "",
        entries: [],
        version: 1,
        status: "draft",
      }}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.type(screen.getByLabelText("Code"), "priority");
  await user.type(screen.getByLabelText("Name"), "Priority");
  await user.click(screen.getByRole("button", { name: "Add code value" }));
  const entry = screen.getByRole("group", { name: "Code value 1" });
  await user.selectOptions(
    within(entry).getByLabelText("Code value type"),
    "number",
  );
  await user.clear(within(entry).getByLabelText("Code value", { exact: true }));
  await user.type(
    within(entry).getByLabelText("Code value", { exact: true }),
    "1",
  );
  await user.type(within(entry).getByLabelText("Chinese name"), "High");
  await user.type(within(entry).getByLabelText("English name"), "High");
  await user.click(screen.getByRole("button", { name: "Review change" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: update_code_list",
    }),
  ).toBeVisible();
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[1]?.body,
  ).toBe(
    JSON.stringify({
      definition: {
        code: "priority",
        name: "Priority",
        entries: [{ value: 1, label_zh: "High", label_en: "High" }],
        version: 1,
        status: "draft",
      },
    }),
  );
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});
