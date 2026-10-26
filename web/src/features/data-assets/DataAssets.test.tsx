import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AssetAccessForm } from "./AssetAccessForm";
import { AssetAccessHistory } from "./AssetAccessHistory";
import { AssetEditor } from "./AssetEditor";
import { AssetPublication } from "./AssetPublication";
import { AssetSummary } from "./AssetSummary";
import { assetCard, mockAssetFetch } from "./fixtures";

it("prepares a typed asset draft and executes only after approving its frozen plan", async () => {
  const fetch = mockAssetFetch();
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<AssetEditor onChanged={changed} onOpenReceipt={vi.fn()} />);
  await user.type(
    screen.getByRole("textbox", { name: "Chinese name" }),
    "Sales",
  );
  await user.type(screen.getByRole("textbox", { name: "Owner" }), "Analytics");
  await user.type(
    screen.getByRole("textbox", { name: "Referenced object ID" }),
    "sample-dataset",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Tags (comma separated)" }),
    " sales, finance ",
  );
  await user.type(
    screen.getByRole("textbox", { name: "Synonyms (comma separated)" }),
    "receipts",
  );
  await user.click(
    screen.getByRole("button", { name: "Prepare change for review" }),
  );
  const confirm = await screen.findByRole("button", {
    name: "Approve and Create asset draft",
  });
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[1]?.body,
  ).toContain('"tags":["sales","finance"]');
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[0],
  ).toBe("/api/actions/create_data_asset/prepare");
  await user.click(confirm);
  await waitFor(() => {
    expect(changed).toHaveBeenCalledOnce();
  });
  expect(
    fetch.mock.calls.filter(([path]) => path.endsWith("/execute")),
  ).toHaveLength(1);
  expect(await screen.findByText("Change executed.")).toBeVisible();
});

it("edits an existing asset with its full definition and preserves the referenced version", async () => {
  const fetch = mockAssetFetch();
  const user = userEvent.setup();
  render(
    <AssetEditor
      asset={assetCard.asset}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.clear(screen.getByRole("textbox", { name: "Owner" }));
  await user.type(screen.getByRole("textbox", { name: "Owner" }), "New owner");
  await user.type(
    screen.getByRole("textbox", { name: "Referenced version (optional)" }),
    "v1",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Classification" }),
    "restricted",
  );
  await user.click(
    screen.getByRole("button", { name: "Prepare change for review" }),
  );
  await screen.findByRole("button", { name: "Approve and Edit asset" });
  const call = fetch.mock.calls.find(([path]) => path.endsWith("/prepare"));
  expect(call?.[0]).toBe("/api/actions/update_data_asset/prepare");
  expect(call?.[1]?.body).toContain('"asset_id":"asset-orders"');
  expect(call?.[1]?.body).toContain('"owner":"New owner"');
  expect(call?.[1]?.body).toContain('"version":"v1"');
});

it.each([
  ["draft", "Publish asset", "publish_data_asset"],
  ["published", "Withdraw asset", "withdraw_data_asset"],
] as const)(
  "prepares the %s publication transition without executing it",
  async (status, label, action) => {
    const fetch = mockAssetFetch();
    render(
      <AssetPublication
        asset={{ ...assetCard.asset, status }}
        onChanged={vi.fn()}
        onOpenReceipt={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: label }));
    await screen.findByRole("button", { name: `Approve and ${label}` });
    expect(
      fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[0],
    ).toBe(`/api/actions/${action}/prepare`);
    expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
      false,
    );
  },
);

it("submits purpose, the chosen operator, UTC expiry and exact requested scopes", async () => {
  const fetch = mockAssetFetch();
  const changed = vi.fn();
  const user = userEvent.setup();
  render(<AssetAccessForm assetId={assetCard.asset.id} onChanged={changed} />);
  const actor = screen.getByRole("textbox", { name: "Operator identity" });
  await user.clear(actor);
  await user.type(actor, "analyst");
  await user.type(
    screen.getByRole("textbox", { name: "Purpose" }),
    "Monthly review",
  );
  fireEvent.change(screen.getByLabelText("Access expires at"), {
    target: { value: "2099-10-28T12:00" },
  });
  await user.click(screen.getByRole("checkbox", { name: "Download" }));
  await user.click(screen.getByRole("button", { name: "Submit request" }));
  expect(
    await screen.findByText("Request submitted and awaiting approval."),
  ).toBeVisible();
  const body = fetch.mock.calls.find(([, init]) => init?.method === "POST")?.[1]
    ?.body;
  expect(JSON.parse(typeof body === "string" ? body : "{}") as unknown).toEqual(
    expect.objectContaining({
      applicant: "analyst",
      purpose: "Monthly review",
      scopes: ["query", "download"],
      expires_at: new Date("2099-10-28T12:00").toISOString(),
    }),
  );
  expect(changed).toHaveBeenCalledOnce();
});

it.each([
  [true, "Approve request"],
  [false, "Reject request"],
] as const)(
  "prepares the access decision %s as a controlled action",
  async (approve, label) => {
    const fetch = mockAssetFetch();
    render(
      <AssetAccessHistory
        assetId={assetCard.asset.id}
        onChanged={vi.fn()}
        onOpenReceipt={vi.fn()}
      />,
    );
    await userEvent.click(await screen.findByRole("button", { name: label }));
    await screen.findByRole("button", {
      name: "Approve and Decide access request",
    });
    const call = fetch.mock.calls.find(([path]) => path.endsWith("/prepare"));
    expect(call?.[0]).toBe("/api/actions/decide_asset_application/prepare");
    expect(call?.[1]?.body).toBe(
      JSON.stringify({ application_id: "application-1", approve, reason: "" }),
    );
    expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
      false,
    );
  },
);

it("revokes through review while preserving grant history", async () => {
  const fetch = mockAssetFetch();
  render(
    <AssetAccessHistory
      assetId={assetCard.asset.id}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Revoke grant" }),
  );
  await screen.findByRole("button", { name: "Approve and Revoke grant" });
  expect(
    fetch.mock.calls.find(([path]) => path.endsWith("/prepare"))?.[0],
  ).toBe("/api/actions/revoke_asset_grant/prepare");
  expect(screen.getByText("grant-1")).toBeVisible();
});

it("shows measured trend and hides empty optional extension positions", () => {
  const { rerender } = render(<AssetSummary card={assetCard} expanded />);
  expect(screen.getByRole("heading", { name: "Quality trend" })).toBeVisible();
  expect(
    screen.queryByRole("heading", { name: "Version release" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/Data standard coverage/)).not.toBeInTheDocument();
  rerender(
    <AssetSummary
      card={{
        ...assetCard,
        version_release: { version: "v2" },
        standard_coverage: 0.8,
      }}
      expanded
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Version release" }),
  ).toBeVisible();
  expect(screen.getByText("Data standard coverage: 0.8")).toBeVisible();
});

it("blocks asset changes during composition and keeps the form available after prepare failure", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify({ detail: "Changed revision" }), {
        status: 409,
      }),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <AssetEditor
      asset={assetCard.asset}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  const name = screen.getByRole("textbox", { name: "Chinese name" });
  fireEvent.compositionStart(name);
  await user.click(
    screen.getByRole("button", { name: "Prepare change for review" }),
  );
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.compositionEnd(name);
  await user.click(
    screen.getByRole("button", { name: "Prepare change for review" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "409 Changed revision",
  );
  expect(name).toBeEnabled();
});
