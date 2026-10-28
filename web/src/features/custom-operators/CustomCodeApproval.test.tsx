import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionRun } from "../../test/actionFixtures";
import {
  customCode,
  customHash,
  customPlan,
} from "../../test/customOperatorFixtures";
import { PlanCard } from "../actions/PlanCard";

import { SubmissionForm } from "./SubmissionForm";

it("shows every source line, hash and advisory finding before signing the exact frozen plan", async () => {
  const fetch = vi.fn((path: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/execute") && init?.method === "POST"
            ? { ...actionRun, action_type: "submit_custom_operator" }
            : { ...customPlan, status: "APPROVED" },
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const { container } = render(
    <PlanCard plan={customPlan} onOpenReceipt={vi.fn()} />,
  );
  expect(container.querySelector(".custom-source code")?.textContent).toBe(
    customCode,
  );
  expect(container.querySelector(".custom-source script")).toBeNull();
  expect(screen.getByText(customHash, { exact: true })).toBeVisible();
  expect(screen.getByText(/Line 3 · risky_capability/)).toBeVisible();
  expect(screen.getByText(/Static findings identify risks/)).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
  await userEvent.click(
    screen.getByRole("button", {
      name: "Approve and register custom operator code",
    }),
  );
  expect(
    await screen.findByText("submit_custom_operator", { selector: "strong" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
  const body = fetch.mock.calls[0]?.[1];
  expect(body?.body).toContain(`"plan_digest":"${customPlan.plan_digest}"`);
});

it("validates hyphenated names using the browser Unicode-sets pattern syntax", async () => {
  render(<SubmissionForm onPrepared={vi.fn()} />);
  const name = screen.getByRole<HTMLInputElement>("textbox", {
    name: "Operator name",
  });
  const pattern = new RegExp(`^(?:${name.pattern})$`, "v");
  expect(pattern.test("filter-lines_2")).toBe(true);
  expect(pattern.test("Invalid-name")).toBe(false);
  const user = userEvent.setup();
  await user.type(name, "filter-lines_2");
  expect(name).toBeValid();
  await user.clear(name);
  await user.type(name, "Invalid-name");
  expect(name).toBeInvalid();
});
