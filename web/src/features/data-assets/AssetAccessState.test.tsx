import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AssetAccessForm } from "./AssetAccessForm";
import { AssetAccessHistory } from "./AssetAccessHistory";
import { application, assetCard, grant } from "./fixtures";

it("reuses the same explicit operation ID when retrying an unchanged application", async () => {
  const fetch = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>(
    () => Promise.resolve(new Response(JSON.stringify(application))),
  );
  fetch.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: "Temporary failure" }), {
      status: 503,
    }),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AssetAccessForm assetId={assetCard.asset.id} onChanged={vi.fn()} />);
  await user.type(
    screen.getByRole("textbox", { name: "Purpose" }),
    "Retry review",
  );
  fireEvent.change(screen.getByLabelText("Access expires at"), {
    target: { value: "2099-10-28T12:00" },
  });
  await user.click(screen.getByRole("button", { name: "Submit request" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "503 Temporary failure",
  );
  await user.click(screen.getByRole("button", { name: "Submit request" }));
  await screen.findByText("Request submitted and awaiting approval.");
  const first = fetch.mock.calls[0]?.[1]?.body;
  expect(first).toMatch(/"operation_id":"[a-f0-9-]+"/);
  expect(fetch.mock.calls[1]?.[1]?.body).toBe(first);
});

it("retains expired and revoked grants while allowing revocation only for an active grant", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path.includes("/grants?")
              ? [
                  grant,
                  {
                    ...grant,
                    id: "expired-grant",
                    expires_at: "2000-01-01T00:00:00Z",
                  },
                  {
                    ...grant,
                    id: "revoked-grant",
                    revoked_at: "2026-10-27T00:00:00Z",
                    revoked_by: "local",
                  },
                ]
              : [],
          ),
        ),
      ),
    ),
  );
  render(
    <AssetAccessHistory
      assetId={assetCard.asset.id}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(await screen.findByText("Expired")).toBeVisible();
  expect(screen.getByText("Revoked")).toBeVisible();
  expect(screen.getAllByRole("button", { name: "Revoke grant" })).toHaveLength(
    1,
  );
});
