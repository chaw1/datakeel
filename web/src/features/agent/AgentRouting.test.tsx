import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { agentEvent } from "../../test/agentFixtures";

import { AgentRouting } from "./AgentRouting";

it("links a route suggestion to a prefilled form without running it", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  render(
    <AgentRouting
      event={agentEvent("route", {
        route: {
          workflow_id: "low-quality-cleanup",
          score: 2,
          reason: "Complete cleanup requested",
          branch: "keyword",
          candidates: [{ workflow_id: "low-quality-cleanup", score: 2 }],
          inputs: { dataset_id: "data / 1" },
        },
      })}
    />,
  );
  expect(screen.getByRole("link", { name: "Run as workflow" })).toHaveAttribute(
    "href",
    "#/workflows?workflow=low-quality-cleanup&dataset=data+%2F+1",
  );
  expect(screen.getByText(/Match score 2/)).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
});
it("hides free-agent decisions and folds persisted model fallback information", async () => {
  const { rerender, container } = render(
    <AgentRouting
      event={agentEvent("route", {
        route: {
          workflow_id: null,
          score: 0,
          reason: "No match",
          branch: "free_agent",
          candidates: [],
          inputs: { dataset_id: null },
        },
      })}
    />,
  );
  expect(container).toBeEmptyDOMElement();
  rerender(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <AgentRouting
        event={agentEvent("done", {
          model_routes: [
            {
              tier: "high_risk",
              model: "fallback-model",
              pinned: false,
              fallback_reason: "HTTP 429",
              attempt: 2,
            },
          ],
        })}
      />
    </I18nContext.Provider>,
  );
  expect(screen.getByText("受控动作规划")).toBeVisible();
  expect(screen.getAllByText("fallback-model")[0]).toBeVisible();
  const reason = screen.getByText(/备用尝试 2：HTTP 429/);
  expect(reason).not.toBeVisible();
  await userEvent.click(screen.getByText(/1 次备用切换/));
  expect(reason).toBeVisible();
});

it("combines all model calls in one compact row per turn without a details control", () => {
  const { container } = render(
    <AgentRouting
      event={agentEvent("done", {
        model_routes: [
          { tier: "simple", model: "reader", pinned: false, attempt: 1 },
          { tier: "multi_step", model: "planner", pinned: false, attempt: 1 },
          { tier: "multi_step", model: "planner", pinned: false, attempt: 1 },
          { tier: "high_risk", model: "controller", pinned: false, attempt: 1 },
        ],
      })}
    />,
  );
  expect(container.querySelectorAll(".model-routing")).toHaveLength(1);
  expect(container.querySelector("details")).toBeNull();
  expect(screen.getByLabelText("Model routing")).toHaveTextContent(
    "Simple read → Multi-step tools → Controlled action planning · controller · Selected by tier · 4 model calls",
  );
});
