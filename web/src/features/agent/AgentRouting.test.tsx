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
          classifier_used: false,
          requires_confirmation: false,
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
  expect(screen.getByText("Review the inputs before starting.")).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
});

it.each(["en", "zh"] as const)(
  "explains a classified mutation in %s and links to its existing confirmation form",
  async (locale) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <AgentRouting
          event={agentEvent("route", {
            route: {
              workflow_id: "metric-change",
              score: 1,
              reason: "Classifier selected a partial rule candidate",
              branch: "classifier",
              classifier_used: true,
              classifier_selection: "metric-change",
              verification_passed: true,
              requires_confirmation: true,
              candidates: [{ workflow_id: "metric-change", score: 1 }],
            },
          })}
        />
      </I18nContext.Provider>,
    );
    expect(
      screen.getByText(
        locale === "en"
          ? "This workflow changes data. Review and confirm the inputs in the workflow form before starting."
          : "此工作流会更改数据，请在工作流表单确认后启动。",
      ),
    ).toBeVisible();
    const start = screen.getByRole("link", {
      name: locale === "en" ? "Run as workflow" : "按工作流运行",
    });
    expect(start).toHaveAttribute("href", "#/workflows?workflow=metric-change");
    await userEvent.click(start);
    expect(fetch).not.toHaveBeenCalled();
  },
);
it("hides free-agent decisions and folds persisted model fallback information", async () => {
  const { rerender, container } = render(
    <AgentRouting
      event={agentEvent("route", {
        route: {
          workflow_id: null,
          score: 0,
          reason: "No match",
          branch: "free_agent",
          classifier_used: false,
          requires_confirmation: false,
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
