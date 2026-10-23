import { actionPlan, actionRun } from "./actionFixtures";
import { dataset, task } from "./fixtures";

import type { DashboardSnapshot } from "../app/useDashboard";

export const dashboard: DashboardSnapshot = {
  datasets: [
    { ...dataset, quality_score: 59 },
    { ...dataset, id: "boundary", name: "Boundary dataset", quality_score: 60 },
    { ...dataset, id: "unknown", name: "Unknown score", quality_score: null },
  ],
  approvals: [actionPlan],
  tasks: [{ ...task, state: "RUNNING", progress: 50 }],
  actions: [actionRun],
};
