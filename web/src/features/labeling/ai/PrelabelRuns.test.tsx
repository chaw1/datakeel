import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../../i18n/context";
import { labelingProject } from "../../../test/labelingFixtures";

import { PrelabelPanel } from "./PrelabelPanel";
import { PROGRESS_REFRESH_MS } from "./PrelabelRuns";

import type { components } from "../../../api/generated";
import type { ProjectWorkbench } from "../../../api/production";

type Progress = components["schemas"]["PrelabelProgress"];

const updated = "2026-10-31T08:00:00Z";
function run(overrides: Partial<Progress> = {}): Progress {
  return {
    run_id: "run-1",
    model_id: "model-1",
    model_name: "qwen-vl",
    model_version: "2026-10",
    status: "running",
    planned_images: 40,
    completed_images: 12,
    failed_images: 1,
    spent: 0.01234,
    budget: 0.5,
    currency: "CNY",
    stopped: false,
    held_drafts: 0,
    started_at: "2026-10-31T07:59:00Z",
    updated_at: updated,
    ...overrides,
  };
}
function withRuns(runs: Progress[]): ProjectWorkbench {
  return { ...labelingProject, prelabel_progress: runs };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

it("lists each run with images, failures, held drafts, spend against budget and when it last moved", () => {
  render(
    <PrelabelPanel
      data={withRuns([
        run(),
        run({
          run_id: "run-0",
          status: "completed",
          completed_images: 40,
          failed_images: 0,
          spent: 0.5,
          stopped: true,
          held_drafts: 3,
          budget: null,
          currency: null,
        }),
      ])}
    />,
  );
  const table = screen.getByRole("table", { name: "Prelabel runs" });
  const time = new Date(updated).toLocaleString("en");
  expect(
    within(table).getByRole("row", {
      name: `qwen-vl@2026-10 Running 12/40 1 0.0123 CNY / 0.5000 CNY ${time}`,
    }),
  ).toBeVisible();
  expect(
    within(table).getByRole("row", {
      name: `qwen-vl@2026-10 Completed Stopped at budget Held by someone, drafts only: 3 40/40 0 0.5000 / no cap ${time}`,
    }),
  ).toBeVisible();
});

it("names run states in Chinese", () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: () => undefined, t: translator("zh") }}
    >
      <PrelabelPanel
        data={withRuns([
          run({ status: "failed" }),
          run({ run_id: "run-2", status: "abandoned", held_drafts: 2 }),
        ])}
      />
    </I18nContext.Provider>,
  );
  const table = screen.getByRole("table", { name: "预标注运行进度" });
  expect(within(table).getByText("失败")).toBeVisible();
  expect(within(table).getByText("已中断")).toBeVisible();
  expect(within(table).getByText("有人持有，只写了草稿 2 条")).toBeVisible();
});

it("refreshes every five seconds while a run is going and stops when none is", () => {
  const onRefresh = vi.fn();
  const { rerender, unmount } = render(
    <PrelabelPanel data={withRuns([run()])} onRefresh={onRefresh} />,
  );
  act(() => {
    vi.advanceTimersByTime(PROGRESS_REFRESH_MS - 1);
  });
  expect(onRefresh).not.toHaveBeenCalled();
  act(() => {
    vi.advanceTimersByTime(1);
  });
  expect(onRefresh).toHaveBeenCalledTimes(1);
  rerender(
    <PrelabelPanel
      data={withRuns([run({ completed_images: 20 })])}
      onRefresh={onRefresh}
    />,
  );
  act(() => {
    vi.advanceTimersByTime(PROGRESS_REFRESH_MS);
  });
  expect(onRefresh).toHaveBeenCalledTimes(2);
  rerender(
    <PrelabelPanel
      data={withRuns([run({ status: "completed" })])}
      onRefresh={onRefresh}
    />,
  );
  act(() => {
    vi.advanceTimersByTime(PROGRESS_REFRESH_MS * 3);
  });
  expect(onRefresh).toHaveBeenCalledTimes(2);
  rerender(<PrelabelPanel data={withRuns([run()])} onRefresh={onRefresh} />);
  unmount();
  act(() => {
    vi.advanceTimersByTime(PROGRESS_REFRESH_MS * 3);
  });
  expect(onRefresh).toHaveBeenCalledTimes(2);
});

it("does not poll or show a table when no cloud run exists", () => {
  const onRefresh = vi.fn();
  render(<PrelabelPanel data={labelingProject} onRefresh={onRefresh} />);
  act(() => {
    vi.advanceTimersByTime(PROGRESS_REFRESH_MS * 2);
  });
  expect(onRefresh).not.toHaveBeenCalled();
  expect(screen.queryByRole("table", { name: "Prelabel runs" })).toBeNull();
});
