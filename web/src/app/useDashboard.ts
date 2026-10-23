import { useCallback, useEffect, useState } from "react";

import { get } from "../api/client";

import type { components } from "../api/generated";
import type { ActionPlan, ActionRun, Task } from "../api/types";

export type DatasetSummary = components["schemas"]["DatasetQualityView"];
export interface DashboardSnapshot {
  datasets: DatasetSummary[];
  approvals: ActionPlan[];
  tasks: Task[];
  actions: ActionRun[];
}
const empty: DashboardSnapshot = {
  datasets: [],
  approvals: [],
  tasks: [],
  actions: [],
};
export function useDashboard() {
  const [value, setValue] = useState(empty);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => {
    setRevision((n) => n + 1);
  }, []);
  useEffect(() => {
    let active = true;
    let inFlight = false;
    async function load() {
      if (inFlight) return;
      inFlight = true;
      try {
        const [datasets, approvals, tasks, actions] = await Promise.all([
          get<DatasetSummary[]>("/api/datasets?include=quality"),
          get<ActionPlan[]>("/api/approvals"),
          get<Task[]>("/api/tasks"),
          get<ActionRun[]>("/api/actions/runs"),
        ]);
        if (active) {
          setValue({ datasets, approvals, tasks, actions });
          setError("");
        }
      } catch (reason) {
        if (active)
          setError(reason instanceof Error ? reason.message : String(reason));
      } finally {
        inFlight = false;
        if (active) setLoading(false);
      }
    }
    void load();
    const timer = window.setInterval(() => void load(), 10_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [revision]);
  return { value, error, loading, reload };
}
