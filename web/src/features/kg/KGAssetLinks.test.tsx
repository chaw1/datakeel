import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { actionRun } from "../../test/actionFixtures";

import { KGAssetLinks } from "./KGAssetLinks";
import { KGEntityDrawer } from "./KGEntityDrawer";
import { metricEntity, salesLink, tableLink } from "./linkFixtures";

function mockLinks() {
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path === "/api/evidence/assertions/decide"
            ? actionRun
            : [salesLink, tableLink],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("shows targets, exact match evidence, unique/ambiguous tiers and object links", async () => {
  const fetch = mockLinks();
  render(<KGAssetLinks datasetId="docs-1" />);
  expect(
    await screen.findByText("营业额 exactly matches metric synonym"),
  ).toBeVisible();
  expect(screen.getByText("Unique match")).toBeVisible();
  expect(screen.getByText("Ambiguous match")).toBeVisible();
  expect(screen.getByRole("link", { name: "销售额" })).toHaveAttribute(
    "href",
    "#/object/metric/sales_revenue?tab=relations",
  );
  expect(screen.getByRole("link", { name: "sales" })).toHaveAttribute(
    "href",
    "#/object/table/crm%2Fmain%2Fsales?tab=relations",
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/kg/links?dataset_id=docs-1",
    expect.anything(),
  );
  const table = screen.getByRole("table", {
    name: "Asset links · link.maps_to",
  });
  expect(within(table).getByText("Candidate")).toBeVisible();
  expect(within(table).getByText("Accepted")).toBeVisible();
});

it("filters link assertions, clears selections, and submits exactly the displayed selected IDs", async () => {
  const fetch = mockLinks();
  const user = userEvent.setup();
  const changed = vi.fn();
  render(<KGAssetLinks datasetId="docs-1" onChanged={changed} />);
  await user.click(
    await screen.findByLabelText("Select all displayed asset links"),
  );
  expect(screen.getByText("2 selected")).toBeVisible();
  await user.selectOptions(screen.getByLabelText("Review status"), "candidate");
  expect(screen.getByText("0 selected")).toBeVisible();
  expect(screen.queryByRole("link", { name: "sales" })).not.toBeInTheDocument();
  await user.click(screen.getByLabelText("Select all displayed asset links"));
  await user.click(screen.getByRole("button", { name: "Accept selected" }));
  expect(
    await screen.findByText("The selected decisions were saved."),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/evidence/assertions/decide",
    expect.objectContaining({
      body: JSON.stringify({
        assertion_ids: ["sales-link"],
        status: "accepted",
        reason: "Reviewed asset links in the knowledge graph workspace",
      }),
    }),
  );
  expect(changed).toHaveBeenCalledOnce();
});

it("supports direct rejection and reports failed decisions without claiming success", async () => {
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path === "/api/evidence/assertions/decide"
            ? {
                ...actionRun,
                status: "FAILED",
                error: "Decision was not saved",
              }
            : [salesLink],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<KGAssetLinks entityId="entity-1" />);
  await user.click(await screen.findByRole("button", { name: "Reject link" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Decision was not saved",
  );
  expect(
    screen.queryByText("The selected decisions were saved."),
  ).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/kg/entities/entity-1/links",
    expect.anything(),
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/evidence/assertions/decide",
    expect.objectContaining({
      body: JSON.stringify({
        assertion_ids: ["sales-link"],
        status: "rejected",
        reason: "Reviewed asset links in the knowledge graph workspace",
      }),
    }),
  );
});

it("adds asset review to data entity details and translates the panel in Chinese", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  mockLinks();
  render(
    <I18nProvider>
      <KGEntityDrawer
        entity={{ ...metricEntity, mentions: [], mention_count: 0 }}
        versionId="v1"
        onClose={vi.fn()}
      />
    </I18nProvider>,
  );
  const panel = screen.getByRole("region", { name: "对应资产" });
  expect(await within(panel).findByText("歧义匹配")).toBeVisible();
  expect(
    within(panel).getAllByRole("button", { name: "接受关联" }),
  ).toHaveLength(2);
  expect(within(panel).getByRole("link", { name: "销售额" })).toBeVisible();
});

it("distinguishes failed reads from an empty set and retries safely", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Links unavailable" }), {
        status: 503,
      }),
    )
    .mockResolvedValue(new Response("[]"));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<KGAssetLinks entityId="entity-1" />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Links unavailable",
  );
  expect(
    screen.queryByText("No corresponding catalog asset is registered."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => {
    expect(
      screen.getByText("No corresponding catalog asset is registered."),
    ).toBeVisible();
  });
});
