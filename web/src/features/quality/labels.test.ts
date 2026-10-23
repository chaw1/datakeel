import { expect, it } from "vitest";

import { translator } from "../../i18n/context";
import { quality } from "../../test/fixtures";

import { qualityGrade, qualityIssueMessage, qualitySeverity } from "./labels";

it("translates grade and severity badges instead of exposing internal enum values", () => {
  const t = translator("zh");
  expect(qualityGrade("good", t)).toBe("良好");
  expect(qualityGrade("excellent", t)).toBe("优秀");
  expect(qualityGrade("fair", t)).toBe("一般");
  expect(qualityGrade("poor", t)).toBe("较差");
  expect(qualitySeverity("critical", t)).toBe("严重");
  expect(qualitySeverity("warning", t)).toBe("警告");
  expect(qualityGrade(undefined, t, "waitingForAnalysis")).toBe("等待分析");
});

it("localizes built-in issue codes using measured values and preserves custom messages", () => {
  const t = translator("zh");
  const dimensions = {
    ...quality.dimensions,
    completeness: { ...quality.dimensions.completeness, score: 58.5 },
  };
  const issue = {
    dimension: "annotation",
    severity: "warning",
    message: "Original issue text",
  };
  expect(
    qualityIssueMessage(
      { ...issue, code: "annotation_excluded" },
      dimensions,
      t,
    ),
  ).toBe("暂无标注证据，其他维度权重已归一化。");
  expect(
    qualityIssueMessage({ ...issue, code: "empty_dataset" }, dimensions, t),
  ).toBe("这个数据集没有文件。");
  expect(
    qualityIssueMessage(
      {
        ...issue,
        code: "completeness_below_target",
        dimension: "completeness",
      },
      dimensions,
      t,
    ),
  ).toBe("完整性：58.50/100；请查看维度详情中的实测证据。");
  expect(
    qualityIssueMessage(
      { ...issue, code: "custom_below_target", dimension: "custom" },
      dimensions,
      t,
    ),
  ).toBe("Original issue text");
  expect(qualityIssueMessage(issue, dimensions, t)).toBe("Original issue text");
});
