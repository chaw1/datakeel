import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { assetCard, mockAssetFetch } from "../features/data-assets/fixtures";
import { I18nProvider } from "../i18n/I18nProvider";

import { DataAssetsPage } from "./DataAssetsPage";

it("renders measured cards and sends search, classification, tag and contractual sorting to the market", async () => {
  const fetch = mockAssetFetch();
  const user = userEvent.setup();
  render(<DataAssetsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByRole("heading", { name: "Orders asset" }),
  ).toBeVisible();
  expect(screen.getByText("94.5")).toBeVisible();
  expect(screen.getByText("12")).toBeVisible();
  expect(screen.getByText("3")).toBeVisible();
  expect(screen.getByRole("link", { name: /Orders asset/ })).toHaveAttribute(
    "href",
    "#/data-assets?asset=asset-orders",
  );
  await user.type(screen.getByRole("searchbox"), "Receipts");
  await user.click(screen.getByRole("button", { name: "Search assets" }));
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Classification" }),
    "request",
  );
  await user.type(screen.getByRole("textbox", { name: "Tag" }), "retail");
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Sort by" }),
    "quality",
  );
  await user.click(
    screen.getByRole("checkbox", {
      name: "Include drafts and withdrawn assets",
    }),
  );
  await waitFor(() => {
    const path = fetch.mock.calls.at(-1)?.[0] ?? "";
    const params = new URL(path, "http://localhost").searchParams;
    expect(params.get("search")).toBe("Receipts");
    expect(params.get("classification")).toBe("request");
    expect(params.get("tag")).toBe("retail");
    expect(params.get("sort")).toBe("quality");
    expect(params.get("include_unpublished")).toBe("true");
  });
});

it("opens the draft editor and supports per-person audit across all assets", async () => {
  const fetch = mockAssetFetch();
  const user = userEvent.setup();
  render(<DataAssetsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  await screen.findByRole("heading", { name: "Orders asset" });
  await user.click(screen.getByRole("button", { name: "Create asset draft" }));
  expect(
    screen.getByRole("textbox", { name: "Referenced object ID" }),
  ).toBeVisible();
  await user.click(
    screen.getByRole("button", {
      name: "View audit across assets by operator",
    }),
  );
  expect(await screen.findByText("grant-1")).toBeVisible();
  await user.type(
    screen.getByRole("textbox", { name: "Filter audit by operator" }),
    "reviewer",
  );
  await user.click(screen.getByRole("button", { name: "Search audit" }));
  await waitFor(() => {
    const params = new URL(
      fetch.mock.calls.at(-1)?.[0] ?? "",
      "http://localhost",
    ).searchParams;
    expect(params.get("actor")).toBe("reviewer");
    expect(params.has("asset_id")).toBe(false);
  });
});

it("opens asset detail with request progress, grants, immutable audit and history", async () => {
  window.location.hash = "#/data-assets?asset=asset-orders";
  mockAssetFetch();
  render(<DataAssetsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(
    await screen.findByRole("heading", { name: "Orders asset" }),
  ).toBeVisible();
  expect(await screen.findByText("Quarterly review")).toBeVisible();
  expect(screen.getByRole("heading", { name: "Usage audit" })).toBeVisible();
  expect(screen.getByRole("heading", { name: "Change history" })).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Open referenced object" }),
  ).toHaveAttribute(
    "href",
    expect.stringContaining("commerce%2Fmain%2Forders"),
  );
  expect(screen.getByRole("button", { name: "Withdraw asset" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Approve request" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Revoke grant" })).toBeVisible();
  expect(
    screen.getByText(assetCard.asset.definition.instructions),
  ).toBeVisible();
});

it("renders the market and asset form in Chinese", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  mockAssetFetch();
  const user = userEvent.setup();
  render(
    <I18nProvider>
      <DataAssetsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />
    </I18nProvider>,
  );
  expect(await screen.findByRole("heading", { name: "Orders" })).toBeVisible();
  expect(screen.getByRole("combobox", { name: "资产分级" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "创建资产草稿" }));
  expect(screen.getByRole("textbox", { name: "脱敏样例" })).toBeVisible();
});

it("reports a market error and retries without losing filters", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Market unavailable" }), {
        status: 503,
      }),
    )
    .mockImplementation(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ items: [], total: 0, offset: 0, limit: 100 }),
        ),
      ),
    );
  vi.stubGlobal("fetch", fetch);
  render(<DataAssetsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "503 Market unavailable",
  );
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No matching assets.")).toBeVisible();
});

it("keeps exactly one request, audit and history section after submitting and refreshing detail", async () => {
  window.location.hash = "#/data-assets?asset=asset-orders";
  mockAssetFetch();
  const user = userEvent.setup();
  render(<DataAssetsPage onDataChanged={vi.fn()} onOpenReceipt={vi.fn()} />);
  await screen.findByRole("heading", { name: "Orders asset" });
  await user.type(
    screen.getByRole("textbox", { name: "Purpose" }),
    "Fresh request",
  );
  fireEvent.change(screen.getByLabelText("Access expires at"), {
    target: { value: "2099-10-28T12:00" },
  });
  await user.click(screen.getByRole("button", { name: "Submit request" }));
  await screen.findByText("Request submitted and awaiting approval.");
  await waitFor(() => {
    expect(
      screen.getAllByRole("heading", {
        name: "Requests and approval progress",
      }),
    ).toHaveLength(1);
    expect(
      screen.getAllByRole("heading", { name: "Usage audit" }),
    ).toHaveLength(1);
    expect(
      screen.getAllByRole("heading", { name: "Change history" }),
    ).toHaveLength(1);
  });
  expect(
    await screen.findByRole("button", { name: "Approve request" }),
  ).toBeVisible();
});
