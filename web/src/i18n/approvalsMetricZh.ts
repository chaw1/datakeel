import type { approvalsMetricEn } from "./approvalsMetricEn";

export const approvalsMetricZh: Record<keyof typeof approvalsMetricEn, string> =
  {
    approvalMetricImpactSummary: "{count} 个对象",
    approvalMetricVersions: "版本 {from} → {to}",
    approvalMetricLoading: "正在读取指标版本…",
    approvalMetricUnavailable: "无法读取指标版本。",
  };
