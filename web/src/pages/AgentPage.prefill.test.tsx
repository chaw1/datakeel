import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { conversation } from "../test/agentFixtures";
import { dataset } from "../test/fixtures";

import { AgentPage } from "./AgentPage";

const props = {
  datasets: [dataset],
  datasetId: "",
  conversationId: "",
  onConversation: vi.fn(),
  onDataChanged: vi.fn(),
  onOpenReceipt: vi.fn(),
  onTrace: vi.fn(),
};

it("shows an object draft without a conversation and carries it into an explicit new one", async () => {
  window.location.hash = `#/agent?${new URLSearchParams({
    prompt: "Inspect this dataset",
    dataset: dataset.id,
  })}`;
  let created = false;
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (init?.method === "POST") created = true;
    const value =
      path === "/api/agent/conversations" && init?.method !== "POST"
        ? created
          ? [conversation]
          : []
        : conversation;
    return Promise.resolve(new Response(JSON.stringify(value)));
  });
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} />);
  await screen.findByText("Start a conversation to explore this workspace.");
  const input = screen.getByRole("textbox", { name: "Message" });
  expect(input).toHaveValue("Inspect this dataset");
  expect(input).toBeDisabled();
  expect(screen.getByLabelText("Dataset for a new conversation")).toHaveValue(
    dataset.id,
  );
  expect(
    fetch.mock.calls.every(
      ([, init]) => !init?.method || init.method === "GET",
    ),
  ).toBe(true);
  await userEvent.click(
    screen.getByRole("button", { name: "New conversation" }),
  );
  await waitFor(() => {
    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
  });
  expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(
    "Inspect this dataset",
  );
  expect(
    fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(1);
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/messages"))).toBe(
    false,
  );
});

it("opens the conversation referenced by a signature sheet", async () => {
  window.location.hash = `#/agent?conversation=${conversation.id}`;
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path === "/api/agent/conversations" ? [conversation] : conversation,
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<AgentPage {...props} conversationId="some-other-conversation" />);
  await waitFor(() => {
    expect(screen.getByRole("textbox", { name: "Message" })).toBeEnabled();
  });
  expect(
    fetch.mock.calls.some(([path]) => path.endsWith(`/${conversation.id}`)),
  ).toBe(true);
  expect(
    fetch.mock.calls.some(([path]) =>
      path.endsWith("/some-other-conversation"),
    ),
  ).toBe(false);
});
