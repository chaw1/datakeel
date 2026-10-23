import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ontology } from "../test/actionFixtures";

import { OntologyPage } from "./OntologyPage";
it("renders the versioned ontology registry", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(ontology)))),
  );
  render(<OntologyPage />);
  expect(
    await screen.findByRole("button", { name: "Object types 1" }),
  ).toBeVisible();
});

it("shows the real empty state after a successful empty response", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            ...ontology,
            object_types: [],
            link_types: [],
            functions: [],
            actions: [],
          }),
        ),
      ),
    ),
  );
  render(<OntologyPage />);
  expect(
    await screen.findByText("No types are registered in this category."),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("shows a server failure without claiming empty results and retries successfully", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Service unavailable" }), {
        status: 500,
      }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify(ontology)));
  vi.stubGlobal("fetch", fetch);
  render(<OntologyPage />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "500 Service unavailable",
  );
  expect(
    screen.queryByText("No types are registered in this category."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(
    await screen.findByRole("button", { name: "Object types 1" }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledTimes(2);
});
