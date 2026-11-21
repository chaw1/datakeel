import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";
import { conversation } from "../../test/agentFixtures";
import { dataset } from "../../test/fixtures";

import { ConversationSidebar } from "./ConversationSidebar";

it("does not create or switch conversations during composition", async () => {
  const create = vi.fn();
  const select = vi.fn();
  const user = userEvent.setup();
  render(
    <ConversationSidebar
      conversations={[conversation]}
      datasets={[dataset]}
      selectedId=""
      datasetId={dataset.id}
      creating={false}
      disabled={false}
      onCreate={create}
      onSelect={select}
    />,
  );
  expect(screen.queryByRole("searchbox")).toBeNull();
  expect(screen.getByText("Turns: 0")).toBeVisible();
  expect(screen.queryByText(/Pending plans:/)).toBeNull();
  const button = screen.getByRole("button", { name: "New conversation" });
  const existing = screen.getByRole("button", {
    name: /^Conversation conversa/,
  });
  fireEvent.compositionStart(button);
  await user.click(button);
  await user.click(existing);
  expect(create).not.toHaveBeenCalled();
  expect(select).not.toHaveBeenCalled();
  fireEvent.compositionEnd(button);
  expect(fireEvent.keyDown(button, { key: "Enter", isComposing: true })).toBe(
    false,
  );
  expect(fireEvent.keyDown(existing, { key: " ", keyCode: 229 })).toBe(false);
  await user.click(button);
  expect(create).toHaveBeenCalledExactlyOnceWith(
    dataset.id,
    false,
    expect.objectContaining({ conversation_tokens: 100000 }),
  );
  await user.click(existing);
  expect(select).toHaveBeenCalledExactlyOnceWith(conversation.id);
});

it("shows controlled search and compact turn and pending-plan metadata", () => {
  const onQueryChange = vi.fn();
  render(
    <ConversationSidebar
      conversations={[
        { ...conversation, turns: 4, pending_plans: [actionPlan] },
      ]}
      datasets={[]}
      selectedId={conversation.id}
      datasetId=""
      creating={false}
      disabled={false}
      query="quality"
      onQueryChange={onQueryChange}
      onCreate={vi.fn()}
      onSelect={vi.fn()}
    />,
  );
  const search = screen.getByRole("searchbox", {
    name: "Search conversations",
  });
  expect(search).toHaveValue("quality");
  fireEvent.change(search, { target: { value: "quality inspect" } });
  expect(onQueryChange).toHaveBeenCalledExactlyOnceWith("quality inspect");
  expect(screen.getByText("Turns: 4")).toBeVisible();
  expect(screen.getByText("Pending plans: 1")).toHaveClass("ui-badge-warn");
});
