import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { actionPlan, actionRun } from "../../test/actionFixtures";

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
const planned: ActionChain = {
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
const intent = (value: Partial<IntentResult>): IntentResult => ({
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
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const body = key in routes ? routes[key] : [];
    return Promise.resolve(Response.json(body));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
afterEach(() => {
  vi.unstubAllGlobals();
});

it("shows every step with impact, cost and signature before anything runs", async () => {
  const fetch = respond({ "GET /api/intents/chains/chain-1": planned });
  render(<IntentCard {...props} intent={intent({ chain: planned })} />);
  const steps = await screen.findAllByRole("listitem");
  expect(within(steps[0]).getByText(/Changes 2 objects/)).toBeVisible();
  expect(within(steps[1]).getByText("Needs signature")).toBeVisible();
  expect(screen.getByText("Two people cross-check each task")).toBeVisible();
  expect(screen.getByText(/Nothing has changed yet/)).toBeVisible();
  expect(screen.queryByText("create_label_set")).toBeNull();
  expect(screen.queryByText("publish_label_set")).toBeNull();
  expect(
    fetch.mock.calls.some(([, init]) => init?.method === "POST"),
  ).toBeFalsy();
});

it("runs only after the person confirms, then shows the receipt and the failure", async () => {
  const failed: ActionChain = {
    ...planned,
    status: "failed",
    steps: [
      { ...planned.steps[0], status: "succeeded", run_ids: [actionRun.id] },
      {
        ...planned.steps[1],
        status: "failed",
        error: "Label set version is already published",
      },
    ],
  };
  const fetch = respond({
    "GET /api/intents/chains/chain-1": planned,
    "POST /api/intents/chains/chain-1/run": failed,
    "GET /api/actions/runs": [actionRun],
  });
  render(<IntentCard {...props} intent={intent({ chain: planned })} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Confirm and run" }),
  );
  expect(
    await screen.findByText("Stopped: Label set version is already published"),
  ).toBeVisible();
  expect(await screen.findByLabelText("Receipt")).toBeVisible();
  const resume = screen.getByRole("button", { name: "Resume" });
  await userEvent.click(resume);
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(2);
  expect(posts.every(([url]) => url.endsWith("/chain-1/run"))).toBeTruthy();
});

it("offers the waiting step's plan for a signature and continues afterwards", async () => {
  const waiting: ActionChain = {
    ...planned,
    status: "awaiting_approval",
    steps: [
      { ...planned.steps[0], status: "succeeded" },
      {
        ...planned.steps[1],
        status: "awaiting_approval",
        plan_ids: [actionPlan.id],
      },
    ],
  };
  respond({
    "GET /api/intents/chains/chain-1": waiting,
    [`GET /api/actions/plans/${actionPlan.id}`]: actionPlan,
  });
  render(<IntentCard {...props} intent={intent({ chain: waiting })} />);
  expect(await screen.findByText(/waits in the approval queue/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
});

it("turns candidates into one-click replies and names missing scopes", async () => {
  const onReply = vi.fn();
  const { rerender } = render(
    <IntentCard
      {...props}
      onReply={onReply}
      intent={intent({
        kind: "clarify",
        text: "Which person do you mean?",
        clarification: {
          question: "Which person do you mean?",
          action: "assign_tasks",
          fields: ["assignee"],
          candidates: [{ id: "li", label: "Xiao Li", kind: "user" }],
        },
      })}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /Xiao Li/ }));
  expect(onReply).toHaveBeenCalledWith("li");
  rerender(
    <IntentCard
      {...props}
      intent={intent({
        kind: "refuse",
        text: "You cannot do this.",
        missing_scopes: ["production:manage"],
      })}
    />,
  );
  expect(screen.getByText("production:manage")).toBeVisible();
});

it("speaks Chinese when the interface is Chinese", async () => {
  respond({ "GET /api/intents/chains/chain-1": planned });
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <IntentCard {...props} intent={intent({ chain: planned })} />
    </I18nContext.Provider>,
  );
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "确认执行" })).toBeVisible();
  });
  expect(screen.getByText(/改 2 个对象/)).toBeVisible();
  expect(screen.getByText("试用")).toHaveAttribute(
    "title",
    expect.stringContaining("八成"),
  );
});

it("marks every one-sentence result as a beta feature", () => {
  render(<IntentCard {...props} intent={intent({ kind: "answer" })} />);
  expect(screen.getByText("Beta")).toBeVisible();
  expect(screen.getByText("Beta")).toHaveAttribute(
    "title",
    expect.stringContaining("eight in ten"),
  );
});

it("shows each step's parameters by name, with defaults and the label change marked", async () => {
  const detailed: ActionChain = {
    ...planned,
    steps: [
      {
        ...planned.steps[0],
        details: [
          { label: "Label set", value: "Street scenes", tone: "param" },
          { label: "Added labels", value: "Dog", tone: "added" },
          {
            label: "based on v1",
            value: "1 labels kept · 0 annotations and 0 revisions affected",
            tone: "impact",
          },
          { label: "package size", value: "100 (default)", tone: "default" },
        ],
      },
      planned.steps[1],
    ],
  };
  respond({ "GET /api/intents/chains/chain-1": detailed });
  render(<IntentCard {...props} intent={intent({ chain: detailed })} />);
  expect(await screen.findByText("Street scenes")).toBeVisible();
  expect(screen.getByText("Dog").closest("[data-tone]")).toHaveAttribute(
    "data-tone",
    "added",
  );
  expect(
    screen.getByText("100 (default)").closest("[data-tone]"),
  ).toHaveAttribute("data-tone", "default");
});

it("answers a request the platform cannot do instead of leaving it silent", () => {
  respond({});
  render(
    <IntentCard
      {...props}
      intent={intent({
        kind: "unsupported",
        text: "I cannot do that here. I can: plan and run actions… Could you rephrase?",
      })}
    />,
  );
  expect(screen.getByText("Not something I can do here")).toBeVisible();
  expect(screen.getByText(/Could you rephrase/)).toBeVisible();
});

it("says a failed model call plainly instead of calling it unsupported", () => {
  respond({});
  render(
    <IntentCard
      {...props}
      intent={intent({
        kind: "failed",
        text: "The model call failed (it timed out), so this sentence was not handled and nothing changed. Please try again.",
      })}
    />,
  );
  expect(screen.getByText("Could not handle this")).toBeVisible();
  expect(screen.queryByText("Not something I can do here")).toBeNull();
  expect(screen.getByText(/nothing changed/)).toBeVisible();
});

it("offers choices by name and replies with the chosen object", async () => {
  const onReply = vi.fn();
  respond({});
  render(
    <IntentCard
      {...props}
      onReply={onReply}
      intent={intent({
        kind: "clarify",
        text: "Which person?",
        clarification: {
          question: "Which person?",
          action: "assign_tasks",
          fields: ["actor"],
          candidates: [{ id: "user-7", label: "Li Lei", kind: "user" }],
        },
      })}
    />,
  );
  const choice = screen.getByRole("button", { name: "Li Lei" });
  expect(choice).not.toHaveTextContent("user-7");
  await userEvent.setup().click(choice);
  expect(onReply).toHaveBeenCalledWith("user-7");
});
