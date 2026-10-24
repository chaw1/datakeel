import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { salesLink } from "../features/kg/linkFixtures";
import { actionRun } from "../test/actionFixtures";
import { dataset, version } from "../test/fixtures";
import {
  kgDataset,
  kgProfile,
  kgResult,
  kgRun,
  kgSchema,
  suspect,
} from "../test/kgFixtures";

import { KnowledgeGraphPage } from "./KnowledgeGraphPage";

import type { KGResult } from "../api/kg";

function apiFixture() {
  let result: KGResult = kgResult;
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    let data: unknown = null;
    if (path.endsWith("/versions")) data = [version];
    if (path === "/api/kg/schemas") data = [kgSchema];
    if (path === "/api/kg/profiles") data = [kgProfile];
    if (path.startsWith("/api/kg/runs?")) data = [kgRun];
    if (path === "/api/kg/query") data = result;
    if (path.startsWith("/api/kg/links?")) data = [salesLink];
    if (path === "/api/evidence/assertions/decide") {
      const body = JSON.parse(
        typeof init?.body === "string" ? init.body : "{}",
      ) as {
        status: "accepted" | "rejected";
      };
      result = {
        ...kgResult,
        relations: kgResult.relations.map((row) => ({
          ...row,
          assertion: { ...row.assertion, status: body.status },
        })),
      };
      data = actionRun;
    }
    return Promise.resolve(new Response(JSON.stringify(data)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function renderPage() {
  render(
    <KnowledgeGraphPage
      datasets={[{ ...dataset, id: "legacy" }, kgDataset]}
      datasetId="legacy"
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
}
it("opens the dedicated asset-link review scope without mixing extraction relations", async () => {
  const fetch = apiFixture();
  const user = userEvent.setup();
  renderPage();
  await screen.findByText("Vapor");
  await user.click(screen.getByRole("tab", { name: "Corresponding assets" }));
  expect(
    await screen.findByRole("table", { name: "Asset links · link.maps_to" }),
  ).toBeVisible();
  expect(screen.queryByText("Vapor")).not.toBeInTheDocument();
  expect(
    screen.getByText(
      "Asset links use the latest graph version of each dataset.",
    ),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    `/api/kg/links?dataset_id=${dataset.id}`,
    expect.anything(),
  );
});
it("selects the graph dataset, prioritizes review, and persists batch decisions", async () => {
  const fetch = apiFixture();
  const user = userEvent.setup();
  renderPage();
  expect(screen.getByLabelText("Graph dataset")).toHaveValue(dataset.id);
  const checkbox = await screen.findByRole("checkbox", {
    name: "Select relation Vapor kg.develops Reed",
  });
  expect(document.querySelector("tbody tr")).toHaveAttribute(
    "data-relation-id",
    suspect.assertion.id,
  );
  await user.click(checkbox);
  await user.click(screen.getByRole("button", { name: "Reject selected" }));
  expect(
    await screen.findByText("The selected decisions were saved."),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/evidence/assertions/decide",
    expect.objectContaining({
      body: JSON.stringify({
        assertion_ids: [suspect.assertion.id],
        status: "rejected",
        reason: "Reviewed in the knowledge graph workspace",
      }),
    }),
  );
  await waitFor(() => {
    expect(screen.getAllByText("Rejected")).toHaveLength(3);
  });
  expect(
    screen.getByRole("button", { name: "Accept selected" }),
  ).toBeDisabled();
});
it("filters types and verification in the request and clears checked rows", async () => {
  const fetch = apiFixture();
  const user = userEvent.setup();
  renderPage();
  await user.click(
    await screen.findByRole("checkbox", {
      name: "Select all displayed relations",
    }),
  );
  await user.selectOptions(
    screen.getByLabelText("Entity type"),
    "Organization",
  );
  await user.selectOptions(
    screen.getByLabelText("Source verification"),
    "needs_review",
  );
  await user.selectOptions(screen.getByLabelText("Review status"), "candidate");
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/kg/query",
      expect.objectContaining({
        body: JSON.stringify({
          limit: 200,
          entity_type: "Organization",
          verification: "needs_review",
          status: "candidate",
          dataset_id: dataset.id,
          version_id: version.id,
        }),
      }),
    );
  });
  expect(
    screen.getByRole("button", { name: "Reject selected" }),
  ).toBeDisabled();
});
it("shows partial failures and schema proposals from extraction reports", async () => {
  apiFixture();
  const user = userEvent.setup();
  renderPage();
  await screen.findByText("Vapor");
  await user.click(screen.getByRole("tab", { name: "Extraction runs" }));
  await user.click(
    screen.getByText(/replay-demo · recorded-model/, { selector: "span" }),
  );
  expect(
    screen.getByText("Failed blocks").nextElementSibling,
  ).toHaveTextContent("1");
  expect(screen.getByText("length")).toBeVisible();
  expect(screen.getByText("Characters 30–60")).toBeVisible();
  await user.click(screen.getByRole("tab", { name: "Schema proposals" }));
  await user.click(screen.getByText(/Unknown relation/));
  expect(screen.getByText("invented")).toBeVisible();
  expect(
    within(screen.getByRole("table")).getByText("Cedar develops Reed."),
  ).toBeVisible();
});
it("shows an actionable failure without a false empty successful table", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      Promise.resolve(
        path === "/api/kg/query"
          ? new Response(JSON.stringify({ detail: "Graph read failed" }), {
              status: 500,
            })
          : new Response(
              JSON.stringify(path.endsWith("/versions") ? [version] : []),
            ),
      ),
    ),
  );
  renderPage();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "500 Graph read failed",
  );
  expect(
    screen.queryByText("No graph results match this selection."),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
});
