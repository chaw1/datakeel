import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { pausedWorkflow } from "../../test/workflowFixtures";

import { WorkflowTimeline } from "./WorkflowTimeline";

it("shows a failed step reason and later skipped work without a resume action", () => {
  render(
    <WorkflowTimeline
      run={{
        ...pausedWorkflow,
        status: "FAILED",
        pending_plan_id: null,
        error: "Task timed out; start datakeel worker",
        steps: [
          {
            ...pausedWorkflow.steps[0],
            status: "FAILED",
            error: "Task timed out",
            output: null,
          },
          { ...pausedWorkflow.steps[1], status: "SKIPPED" },
        ],
      }}
      busy={false}
      onResume={vi.fn()}
    />,
  );
  expect(
    screen.getByText("Task timed out; start datakeel worker"),
  ).toBeVisible();
  expect(screen.getByText("Skipped")).toBeVisible();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("renders the paused timeline and explicit resume instruction in Chinese", () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <WorkflowTimeline run={pausedWorkflow} busy={false} onResume={vi.fn()} />
    </I18nContext.Provider>,
  );
  expect(screen.getByRole("link", { name: "查看签批" })).toBeVisible();
  expect(screen.getByRole("button", { name: "签批后继续" })).toBeVisible();
  expect(
    screen.getByText("审阅并签批冻结计划后，返回此处继续工作流。"),
  ).toBeVisible();
  expect(screen.getByText("步骤时间线")).toBeVisible();
  expect(screen.getByText("查找低质文件")).toBeVisible();
  expect(screen.getByText("找到 2 个文件")).toBeVisible();
  expect(screen.getByText("计划已准备，等待签批后继续")).toBeVisible();
});

it.each(["en", "zh"] as const)(
  "keeps raw output folded while showing localized titles and a plain summary in %s",
  async (locale) => {
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <WorkflowTimeline
          run={pausedWorkflow}
          busy={false}
          onResume={vi.fn()}
        />
      </I18nContext.Provider>,
    );
    expect(
      screen.getByText(
        locale === "en" ? "Find low-quality files" : "查找低质文件",
      ),
    ).toBeVisible();
    expect(
      screen.getByText(locale === "en" ? "Found 2 files" : "找到 2 个文件"),
    ).toBeVisible();
    const output = screen.getByText(/"function": "search_files"/);
    expect(output).not.toBeVisible();
    await userEvent.click(
      screen.getByText(locale === "en" ? "Output" : "输出", {
        selector: "summary",
      }),
    );
    expect(output).toBeVisible();
    expect(output.textContent).toBe(
      JSON.stringify(pausedWorkflow.steps[0].output, null, 2),
    );
  },
);
