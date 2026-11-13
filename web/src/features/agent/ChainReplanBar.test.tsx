import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { IntentCard } from "./IntentCard";

import type { ActionChain, IntentResult } from "../../api/intents";

const step = {
  params: {},
  items: [],
  scope: "production:manage",
  attempts: 0,
  plan_ids: [],
  run_ids: [],
  outputs: {},
  error: null,
};

const estimate = {
  object_count: null,
  cost_usd: 0,
  requires_approval: false,
  external: false,
  exact: false,
};

const baseChain: ActionChain = {
  id: "chain-1",
  actor: "local",
  text: "set up",
  language: "en",
  parser: "rules",
  model: null,
  conversation_id: null,
  status: "planned",
  notes: ["Two people cross-check each task"],
  created_at: "2026-10-31T00:00:00Z",
  updated_at: "2026-10-31T00:00:00Z",
  steps: [
    {
      ...step,
      id: "s1",
      action: "create_label_set",
      status: "planned",
      estimate: { ...estimate, object_count: 2 },
    },
    {
      ...step,
      id: "s2",
      action: "publish_label_set",
      status: "planned",
      estimate: { ...estimate, requires_approval: true },
    },
  ],
};

const makeIntent = (value: Partial<IntentResult>): IntentResult => ({
  kind: "plan",
  text: "Nothing changes until you confirm.",
  parser: "rules",
  request: "",
  chain: null,
  clarification: null,
  answer: null,
  missing_scopes: [],
  draft: {},
  ...value,
});

const props = { busy: false, onResolved: vi.fn(), onOpenReceipt: vi.fn() };

function respond(routes: Record<string, unknown>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const body = key in routes ? routes[key] : [];
    return Promise.resolve(Response.json(body));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("plans remaining deferred steps after a succeeded chain without auto-running", async () => {
  const succeededChain: ActionChain = {
    ...baseChain,
    status: "succeeded",
    steps: [{ ...baseChain.steps[0], status: "succeeded" }],
    deferred_steps: [{ id: "s2", action: "assign_tasks", params: {} }],
  };
  const nextChain: ActionChain = {
    ...baseChain,
    id: "chain-2",
    status: "planned",
    steps: [{ ...baseChain.steps[1], id: "s2", action: "assign_tasks" }],
  };
  const fetchMock = respond({
    "GET /api/intents/chains/chain-1": succeededChain,
    "POST /api/intents/chains/chain-1/replan": makeIntent({
      kind: "plan",
      text: "Planned 1 follow-up step.",
      chain: nextChain,
    }),
    "GET /api/intents/chains/chain-2": nextChain,
  });
  render(
    <IntentCard
      {...props}
      intent={makeIntent({ kind: "plan", chain: succeededChain })}
    />,
  );
  const planRemaining = await screen.findByRole("button", {
    name: "Plan remaining steps",
  });
  await userEvent.setup().click(planRemaining);

  await waitFor(() => {
    expect(screen.getByText("Planned 1 follow-up step.")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Confirm and run" }),
    ).toBeEnabled();
  });
  expect(fetchMock).not.toHaveBeenCalledWith(
    "/api/intents/chains/chain-2/run",
    expect.anything(),
  );
});

it("offers live-DB replanning alongside resume on a failed chain", async () => {
  const failedChain: ActionChain = {
    ...baseChain,
    id: "chain-fail",
    status: "failed",
    steps: [
      { ...baseChain.steps[0], status: "succeeded" },
      { ...baseChain.steps[1], status: "failed", error: "approval rejected" },
    ],
  };
  const updatedChain: ActionChain = {
    ...baseChain,
    id: "chain-retry",
    status: "planned",
    steps: [{ ...baseChain.steps[1], status: "planned" }],
  };
  const fetchMock = respond({
    "GET /api/intents/chains/chain-fail": failedChain,
    "POST /api/intents/chains/chain-fail/replan": makeIntent({
      kind: "plan",
      text: "Replanned remaining step.",
      chain: updatedChain,
    }),
    "GET /api/intents/chains/chain-retry": updatedChain,
  });
  render(
    <IntentCard
      {...props}
      intent={makeIntent({ kind: "plan", chain: failedChain })}
    />,
  );
  expect(await screen.findByRole("button", { name: "Resume" })).toBeVisible();
  const replanBtn = screen.getByRole("button", {
    name: "Replan from current state",
  });
  await userEvent.setup().click(replanBtn);

  await waitFor(() => {
    expect(
      screen.getByText(
        "Updated plan ready below. Nothing runs until you confirm.",
      ),
    ).toBeVisible();
  });
  const posts = fetchMock.mock.calls.filter(
    ([url, init]) =>
      url === "/api/intents/chains/chain-fail/replan" &&
      init?.method === "POST",
  );
  expect(posts).toHaveLength(1);
});
