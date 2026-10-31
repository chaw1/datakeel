import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { conversation } from "../test/agentFixtures";
import { dataset } from "../test/fixtures";

import { AgentPage } from "./AgentPage";

const props = {
  datasets: [dataset],
  datasetId: dataset.id,
  conversationId: conversation.id,
  onConversation: vi.fn(),
  onDataChanged: vi.fn(),
  onOpenReceipt: vi.fn(),
  onTrace: vi.fn(),
};
function json(value: unknown) {
  return new Response(JSON.stringify(value));
}

it("says plainly when no configured model can serve a new conversation", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string, init?: RequestInit) =>
    Promise.resolve(
      json(
        path === "/api/agent/conversations/definitions/provider"
          ? {
              provider: "fake",
              model: "fake-demo",
              problem: "unrouted_endpoint",
              endpoint: "llm.example.com",
            }
          : path === "/api/agent/conversations" && init?.method !== "POST"
            ? [conversation]
            : conversation,
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await screen.findByRole("textbox", { name: "Message" });
  expect(screen.queryByText(/configuration problem/)).toBeNull();
  await user.click(screen.getByRole("button", { name: "New conversation" }));
  expect(
    await screen.findByText(
      "No model is available: this is a configuration problem",
    ),
  ).toBeVisible();
  expect(screen.getByText(/llm\.example\.com/)).toBeVisible();
});
