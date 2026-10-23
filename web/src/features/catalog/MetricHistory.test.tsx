import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { metric, metricPlan, metricRun } from "./fixtures";
import { MetricHistory } from "./MetricHistory";

import type { MetricHistory as History } from "../../api/objects";
import type { ActionPlan, ActionRun } from "../../api/types";

const history: History = {
  metric_id: metric.definition.id,
  versions: [
    metric,
    { ...metric, definition: { ...metric.definition, version: 2 } },
  ],
  audit: [],
};
const plan: ActionPlan = {
  ...metricPlan,
  action_type: "rollback_metric",
  canonical_params: { metric_id: metric.definition.id, version: 1 },
  impact: { object_count: 1, total_bytes: 0, external: false },
  manifest: { ...metricPlan.manifest, objects: [], total_bytes: 0 },
};
const run: ActionRun = { ...metricRun, action_type: "rollback_metric" };
function mockRollback() {
  const fetch = vi.fn<(path: string, init?: RequestInit) => Promise<Response>>(
    (path) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path.endsWith("/prepare")
              ? plan
              : path.endsWith("/history")
                ? history
                : run,
          ),
        ),
      ),
  );
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function renderHistory(onChanged = vi.fn()) {
  return render(
    <I18nProvider>
      <MetricHistory
        history={history}
        currentVersion={2}
        onChanged={onChanged}
        onOpenReceipt={vi.fn()}
      />
    </I18nProvider>,
  );
}

it.each([
  ["en", "Roll back to this version", "Current version", "Execute action"],
  ["zh", "回滚到此版本", "当前版本", "执行动作"],
])(
  "reviews a historical rollback in %s before executing the frozen reversible plan",
  async (locale, rollback, current, execute) => {
    localStorage.setItem("datakeel.locale", locale);
    const fetch = mockRollback();
    const changed = vi.fn();
    const user = userEvent.setup();
    const { container } = renderHistory(changed);
    const currentRow = container.querySelector('[data-metric-version="2"]');
    expect(currentRow).toHaveTextContent(current);
    expect(currentRow?.querySelector("button")).toBeNull();
    expect(screen.getAllByRole("button", { name: rollback })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: rollback }));
    const sheet = await screen.findByRole("article", {
      name: /rollback_metric/,
    });
    expect(sheet).toHaveClass("approval-sheet");
    expect(
      fetch.mock.calls.filter(([path]) => path.endsWith("/prepare")),
    ).toHaveLength(1);
    expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
      false,
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/actions/rollback_metric/prepare",
      expect.objectContaining({
        body: JSON.stringify({ metric_id: metric.definition.id, version: 1 }),
      }),
    );
    expect(changed).not.toHaveBeenCalled();
    await user.click(within(sheet).getByRole("button", { name: execute }));
    await waitFor(() => {
      expect(changed).toHaveBeenCalledOnce();
    });
    expect(
      fetch.mock.calls.some(([path]) => path.startsWith("/api/approvals/")),
    ).toBe(false);
    expect(fetch).toHaveBeenLastCalledWith(
      `/api/actions/${plan.id}/execute`,
      expect.objectContaining({
        body: JSON.stringify({
          plan_digest: plan.plan_digest,
          actor: "local",
          operation_id: plan.operation_id,
        }),
      }),
    );
  },
);

it("keeps historical rollback available after a prepare failure", async () => {
  const fetch = mockRollback();
  fetch.mockResolvedValueOnce(
    new Response(JSON.stringify({ detail: "Definition changed" }), {
      status: 409,
    }),
  );
  const user = userEvent.setup();
  renderHistory();
  const button = screen.getByRole("button", {
    name: "Roll back to this version",
  });
  await user.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Definition changed",
  );
  expect(button).toBeEnabled();
  await user.click(button);
  expect(
    await screen.findByRole("article", {
      name: "Action plan: rollback_metric",
    }),
  ).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it.each(["FAILED", "DENIED"] as const)(
  "retains a %s receipt without claiming rollback succeeded",
  async (status) => {
    const fetch = mockRollback();
    fetch.mockImplementation((path) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            path.endsWith("/prepare")
              ? plan
              : path.endsWith("/history")
                ? history
                : { ...run, status, error: "Target changed" },
          ),
        ),
      ),
    );
    const changed = vi.fn();
    const user = userEvent.setup();
    renderHistory(changed);
    await user.click(
      screen.getByRole("button", { name: "Roll back to this version" }),
    );
    await user.click(
      await screen.findByRole("button", { name: "Execute action" }),
    );
    expect(await screen.findByText("Target changed")).toBeVisible();
    expect(changed).not.toHaveBeenCalled();
    expect(
      screen.queryByText(
        "New metric version saved. Future answers use this definition.",
      ),
    ).not.toBeInTheDocument();
  },
);

it("does not prepare a rollback during input composition", () => {
  const fetch = mockRollback();
  renderHistory();
  fireEvent.compositionStart(document);
  fireEvent.click(
    screen.getByRole("button", { name: "Roll back to this version" }),
  );
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.compositionEnd(document);
});
