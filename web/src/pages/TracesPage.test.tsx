import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { conversation, cost, trace } from "../test/agentFixtures";

import { TracesPage } from "./TracesPage";

it("loads selected conversation traces and all three cost grouping dimensions", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.includes("/costs")
            ? [{ ...cost, group_by: path.split("=")[1] }]
            : path.includes("/traces")
              ? [trace]
              : [conversation],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <TracesPage conversationId="conversation-1" onConversation={vi.fn()} />,
  );
  expect(
    await screen.findByRole("region", { name: "Input token segments" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenCalledWith(
    "/api/harness/traces?conversation_id=conversation-1",
    expect.anything(),
  );
  const group = screen.getByRole("combobox", { name: "Group costs by" });
  await user.selectOptions(group, "day");
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/harness/costs?group_by=day",
      expect.anything(),
    );
  });
  await user.selectOptions(group, "model");
  await waitFor(() => {
    expect(fetch).toHaveBeenCalledWith(
      "/api/harness/costs?group_by=model",
      expect.anything(),
    );
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/harness/costs?group_by=conversation",
    expect.anything(),
  );
});

it("shows separate empty trace and cost summaries after successful reads", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response("[]"))),
  );
  render(<TracesPage conversationId="" onConversation={vi.fn()} />);
  expect(
    await screen.findByText("No usage has been recorded yet."),
  ).toBeVisible();
  expect(
    await screen.findByText(
      "No model calls have been recorded for this selection.",
    ),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it.each([
  ["/traces", "No model calls have been recorded for this selection."],
  ["/costs", "No usage has been recorded yet."],
])(
  "retries a failed %s read without presenting it as empty",
  async (endpoint, emptyLabel) => {
    const user = userEvent.setup();
    let failed = false;
    const fetch = vi.fn((path: string) => {
      if (path.includes(endpoint) && !failed) {
        failed = true;
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Service unavailable" }), {
            status: 500,
          }),
        );
      }
      return Promise.resolve(new Response("[]"));
    });
    vi.stubGlobal("fetch", fetch);
    render(<TracesPage conversationId="" onConversation={vi.fn()} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "500 Service unavailable",
    );
    expect(screen.queryByText(emptyLabel)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(emptyLabel)).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      fetch.mock.calls.filter(([path]) => path.includes(endpoint)),
    ).toHaveLength(2);
  },
);
