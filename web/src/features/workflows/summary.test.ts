import { expect, it } from "vitest";

import { translator } from "../../i18n/context";
import { pausedWorkflow } from "../../test/workflowFixtures";

import { workflowStepSummary, workflowStepTitle } from "./summary";

import type { WorkflowRun } from "../../api/workflows";

type Step = WorkflowRun["steps"][number];
const base: Step = { ...pausedWorkflow.steps[0], status: "SUCCEEDED" };
const action = (action_type: string, object_count: number) => ({
  action_type,
  status: "SUCCEEDED",
  receipt: { quality: { object_count }, inputs: [{ asset_id: "dataset-1" }] },
});
const read = (name: string, data: Step["output"]) => ({ function: name, data });

it.each([
  [
    read("search_files", { objects: [{}, {}] }),
    "Found 2 files",
    "找到 2 个文件",
  ],
  [read("search_files", { objects: [] }), "Found 0 files", "找到 0 个文件"],
  [read("get_quality", { total: 100 }), "Quality score 100", "质量分 100"],
  [
    read("get_report", { chapters: [{}, {}, {}] }),
    "Read report with 3 sections",
    "已读取报告，共 3 个章节",
  ],
  [
    read("query_evidence", { total: 12 }),
    "Found 12 evidence items",
    "找到 12 条证据",
  ],
  [
    read("explain_metric", { definition: { name: "Revenue", version: 2 } }),
    "Read Revenue, version 2",
    "已读取「Revenue」口径，版本 2",
  ],
  [
    read("impact_of", { objects: [{}], truncated: false }),
    "Found 1 affected object",
    "找到 1 个受影响对象",
  ],
  [
    read("impact_of", { objects: [{}], truncated: true }),
    "Found at least 1 affected object",
    "找到至少 1 个受影响对象",
  ],
  [
    read("ask_data", { status: "answered", result: { rows: [[4979475]] } }),
    "Answer: 4,979,475",
    "答案：4,979,475",
  ],
  [
    read("ask_data", { status: "unanswerable" }),
    "This question could not be answered",
    "当前问题无法回答",
  ],
  [
    read("ask_data", { status: "clarification" }),
    "The question needs clarification",
    "当前问题需要澄清",
  ],
  [
    { action_type: "run_pipeline", task_id: "task-1", status: "QUEUED" },
    "Pipeline task queued",
    "流水线任务已入队",
  ],
  [action("quarantine_files", 2), "Quarantined 2 files", "已隔离 2 个文件"],
  [
    action("delete_files", 2),
    "Approved and deleted 2 files",
    "已签批并删除 2 个文件",
  ],
  [action("update_metric", 1), "Metric definition updated", "已更新指标口径"],
] satisfies [Step["output"], string, string][])(
  "summarizes actual result fields in both languages: %j",
  (output, en, zh) => {
    const step = { ...base, output };
    expect(
      workflowStepSummary(step, pausedWorkflow, "en", translator("en")),
    ).toBe(en);
    expect(
      workflowStepSummary(step, pausedWorkflow, "zh", translator("zh")),
    ).toBe(zh);
  },
);

it.each([
  [
    { conclusion: "cleaned", file_count: 398 },
    "Conclusion: cleaned; 398 files remaining",
    "结论：已清理，剩余 398 个文件",
  ],
  [
    { conclusion: "no_low_quality_files" },
    "Conclusion: no low-quality files found",
    "结论：未发现低质文件",
  ],
  [
    { conclusion: "healthy", total: 100 },
    "Conclusion: healthy; quality score 100",
    "结论：健康，质量分 100",
  ],
  [
    { conclusion: "needs_review", total: 59.5 },
    "Conclusion: needs review; quality score 59.5",
    "结论：需要复核，质量分 59.5",
  ],
  [
    { before_rows: [[4979475]], after_rows: [[5255975]], rows_equal: false },
    "Before 4,979,475 / after 5,255,975; answer changed",
    "改前 4,979,475 / 改后 5,255,975，答案变了",
  ],
  [
    { before_rows: [[2]], after_rows: [[2]], rows_equal: true },
    "Before 2 / after 2; answer unchanged",
    "改前 2 / 改后 2，答案未变",
  ],
  [
    {
      before_rows: [
        [1, 2],
        [3, 4],
      ],
      after_rows: [[1, 2]],
      rows_equal: false,
    },
    "Before 2 result rows / after 1 result row; answer changed",
    "改前 2 行结果 / 改后 1 行结果，答案变了",
  ],
] satisfies [Step["output"], string, string][])(
  "summarizes final conclusions without serializing JSON: %j",
  (output, en, zh) => {
    const step = { ...base, type: "output", output };
    expect(
      workflowStepSummary(step, pausedWorkflow, "en", translator("en")),
    ).toBe(en);
    expect(
      workflowStepSummary(step, pausedWorkflow, "zh", translator("zh")),
    ).toBe(zh);
  },
);

it("uses the selected edge's localized title and handles both branch outcomes", () => {
  for (const matched of [true, false]) {
    const step = {
      ...base,
      type: "branch",
      output: { matched, next: "delete" },
    };
    expect(
      workflowStepSummary(step, pausedWorkflow, "en", translator("en")),
    ).toBe(
      `${matched ? "Condition met" : "Condition not met"} → Approve and delete files`,
    );
    expect(
      workflowStepSummary(step, pausedWorkflow, "zh", translator("zh")),
    ).toBe(`${matched ? "条件成立" : "条件不成立"} → 签批并删除文件`);
  }
});

it("describes task completion and legacy or unknown outputs without making up results", () => {
  const t = translator("en");
  expect(
    workflowStepSummary(
      { ...base, type: "wait", output: { state: "COMPLETED" } },
      pausedWorkflow,
      "en",
      t,
    ),
  ).toBe("Pipeline task completed");
  for (const output of [
    {},
    "unstructured output",
    read("search_files", {}),
    action("unrecognized_action", 3),
  ]) {
    expect(
      workflowStepSummary({ ...base, output }, pausedWorkflow, "en", t),
    ).toBe("Step completed; details are available in the output");
  }
  expect(workflowStepTitle({ ...base, title: null }, "en", t)).toBe("Tool");
});

it.each([
  ["PENDING", "Waiting for earlier steps"],
  ["RUNNING", "Step in progress"],
  ["PAUSED", "Plan prepared; waiting for approval and continuation"],
  ["SKIPPED", "This step was not taken"],
  ["FAILED", "Step failed; see the reason below"],
] satisfies [Step["status"], string][])(
  "uses %s status before any stale output",
  (status, expected) => {
    const step = { ...base, status, output: action("delete_files", 2) };
    expect(
      workflowStepSummary(step, pausedWorkflow, "en", translator("en")),
    ).toBe(expected);
  },
);

it.each([
  ["FAILED", "Not run: the workflow failed", "未执行：工作流已失败"],
  [
    "INTERRUPTED",
    "Not run: the workflow was interrupted",
    "未执行：工作流已中断",
  ],
] satisfies [WorkflowRun["status"], string, string][])(
  "does not imply that pending steps can continue after %s",
  (status, en, zh) => {
    const run = { ...pausedWorkflow, status };
    const step = { ...base, status: "PENDING" as const, output: null };
    expect(workflowStepSummary(step, run, "en", translator("en"))).toBe(en);
    expect(workflowStepSummary(step, run, "zh", translator("zh"))).toBe(zh);
  },
);
