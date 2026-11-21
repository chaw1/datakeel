import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import {
  createConversation,
  streamMessage,
  streamResume,
} from "../../api/agent";
import { get } from "../../api/client";
import { conversation } from "../../test/agentFixtures";

import { useCopilotSession } from "./useCopilotSession";

vi.mock("../../api/agent", () => ({
  createConversation: vi.fn(),
  streamMessage: vi.fn(),
  streamResume: vi.fn(),
}));
vi.mock("../../api/client", () => ({ get: vi.fn() }));

it("forwards deep-agent mode through lazy creation, then resumes and stops the same session", async () => {
  vi.mocked(get).mockResolvedValue(conversation);
  vi.mocked(createConversation).mockResolvedValue({
    conversation,
    setup: { provider: "fake", model: "fake-demo" },
  });
  vi.mocked(streamMessage).mockResolvedValue(undefined);
  let finish: (() => void) | undefined;
  vi.mocked(streamResume).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const { result, rerender } = renderHook(
    ({ open }) =>
      useCopilotSession({
        open,
        datasetId: "dataset-1",
      }),
    { initialProps: { open: false } },
  );
  expect(get).not.toHaveBeenCalled();
  expect(createConversation).not.toHaveBeenCalled();
  rerender({ open: true });
  await act(() =>
    result.current.sendMessage("Investigate", undefined, "agent"),
  );
  await waitFor(() => {
    expect(streamMessage).toHaveBeenCalledWith(
      conversation.id,
      expect.objectContaining({ content: "Investigate", mode: "agent" }),
      expect.any(Function),
      expect.any(AbortSignal),
    );
    expect(result.current.busy).toBe(false);
  });
  let resumed: Promise<void> | undefined;
  act(() => {
    resumed = result.current.resume("plan-1");
  });
  expect(streamResume).toHaveBeenCalledWith(
    conversation.id,
    expect.objectContaining({ plan_id: "plan-1" }),
    expect.any(Function),
    expect.any(AbortSignal),
  );
  expect(result.current.live.content).toBe("");
  expect(result.current.busy).toBe(true);
  await act(() => result.current.stop());
  expect(vi.mocked(streamResume).mock.calls[0][3].aborted).toBe(true);
  expect(result.current.busy).toBe(false);
  await act(async () => {
    finish?.();
    await resumed;
  });
  expect(createConversation).toHaveBeenCalledTimes(1);
});
