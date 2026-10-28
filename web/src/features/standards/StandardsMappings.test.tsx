import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { mockStandardsFetch, suggestions } from "./fixtures";
import { StandardsMappings } from "./StandardsMappings";

it("explains rule candidates and requires a signed frozen plan before confirming a mapping", async () => {
  const fetch = mockStandardsFetch();
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<StandardsMappings onChanged={changed} onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByText("Column tokens match customer identifier"),
  ).toBeVisible();
  expect(
    screen.getByText("Insufficient evidence for a suggestion."),
  ).toBeVisible();
  expect(fetch.mock.calls.every(([, init]) => init?.method === "GET")).toBe(
    true,
  );
  await user.click(screen.getByRole("button", { name: "Review mapping" }));
  expect(
    await screen.findByRole("article", {
      name: "Action plan: confirm_standard_mapping",
    }),
  ).toBeVisible();
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[1]?.body,
  ).toBe(
    JSON.stringify({
      mapping: {
        column_id: "retail/main/customers/cust_no",
        standard_code: "customer_id",
      },
    }),
  );
  await user.click(
    screen.getByRole("button", {
      name: /Approve and Confirm standard mapping/,
    }),
  );
  await waitFor(() => {
    expect(changed).toHaveBeenCalledOnce();
  });
  const approvals = fetch.mock.calls.findIndex(([path]) =>
    path.startsWith("/api/approvals/"),
  );
  const executed = fetch.mock.calls.findIndex(([path]) =>
    path.endsWith("/execute"),
  );
  expect(approvals).toBeGreaterThan(-1);
  expect(executed).toBeGreaterThan(approvals);
});

it("filters columns and keeps a failed preparation reviewable", async () => {
  const fetch = mockStandardsFetch();
  const original = fetch.getMockImplementation();
  fetch.mockImplementation((input, init) =>
    input.endsWith("/prepare")
      ? Promise.resolve(
          new Response(JSON.stringify({ detail: "Standard was deprecated" }), {
            status: 409,
          }),
        )
      : (original?.(input, init) ?? Promise.reject(new Error("Missing mock"))),
  );
  const user = userEvent.setup();
  render(<StandardsMappings onChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  await screen.findByText("Column tokens match customer identifier");
  await user.type(screen.getByLabelText("Search columns"), "cust_no");
  expect(
    screen.queryByText("Insufficient evidence for a suggestion."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Review mapping" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Standard was deprecated",
  );
});

it("labels low-confidence candidates and leaves confirmation behind explicit review", async () => {
  const fetch = mockStandardsFetch();
  const original = fetch.getMockImplementation();
  fetch.mockImplementation((input, init) =>
    input === "/api/standards/suggestions"
      ? Promise.resolve(
          new Response(
            JSON.stringify([
              {
                ...suggestions[0],
                candidates: suggestions[0].candidates.map((candidate) => ({
                  ...candidate,
                  score: 0.42,
                  low_confidence: true,
                })),
              },
            ]),
          ),
        )
      : (original?.(input, init) ?? Promise.reject(new Error("Missing mock"))),
  );
  render(<StandardsMappings onChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByText("Low confidence · review required"),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "Review mapping" })).toBeEnabled();
  expect(fetch.mock.calls.every(([, init]) => init?.method === "GET")).toBe(
    true,
  );
});
