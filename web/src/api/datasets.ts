import { timestamp } from "../lib/format";

import { get } from "./client";

import type {
  DatasetData,
  FileItem,
  Version,
  Task,
  Graph,
  Quality,
  Report,
} from "./types";
import type { Translate } from "../i18n/context";
import type { MessageKey } from "../i18n/en";

export const blankData: DatasetData = {
  files: [],
  versions: [],
  tasks: [],
  graph: { nodes: [], edges: [], events: [], truncated: false },
  quality: null,
  report: null,
  errors: [],
};
export async function loadDataset(
  id: string,
  t: Translate,
): Promise<DatasetData> {
  const base = `/api/datasets/${encodeURIComponent(id)}`;
  const results = await Promise.allSettled([
    get<FileItem[]>(`${base}/files`),
    get<Version[]>(`${base}/versions`),
    get<Task[]>("/api/tasks"),
    get<Graph>(`/api/lineage/graph?asset=${encodeURIComponent(id)}`),
    get<Quality>(`${base}/quality`),
    get<Report>(`${base}/report`),
  ]);
  const labels: MessageKey[] = [
    "filesTab",
    "versions",
    "pipelineRuns",
    "lineage",
    "quality",
    "report",
  ];
  const [files, versions, tasks, graph, quality, report] = results;
  return {
    files: files.status === "fulfilled" ? files.value : [],
    versions:
      versions.status === "fulfilled"
        ? versions.value.sort(
            (a, b) => timestamp(b.created_at) - timestamp(a.created_at),
          )
        : [],
    tasks:
      tasks.status === "fulfilled"
        ? tasks.value.filter((task) => task.dataset_id === id)
        : [],
    graph: graph.status === "fulfilled" ? graph.value : blankData.graph,
    quality: quality.status === "fulfilled" ? quality.value : null,
    report: report.status === "fulfilled" ? report.value : null,
    errors: results.flatMap((result, index) =>
      result.status === "rejected"
        ? [
            `${t(labels[index])}: ${result.reason instanceof Error ? result.reason.message : t("apiUnavailable")}`,
          ]
        : [],
    ),
  };
}
