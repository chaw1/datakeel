import { useEffect, useRef, useState } from "react";

import { get } from "../../api/client";
import { blankData, loadDataset } from "../../api/datasets";
import { useI18n } from "../../i18n/useI18n";

import type { Dataset, DatasetData, Task } from "../../api/types";
export function useWorkspace(initialDatasetId = "", loadDetails = true) {
  const { t } = useI18n();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selectedId, setSelectedId] = useState(initialDatasetId);
  const [loaded, setLoaded] = useState<{ id: string; data: DatasetData }>({
    id: "",
    data: blankData,
  });
  const data = loaded.id === selectedId ? loaded.data : blankData;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const sequence = useRef(0);
  const selected = datasets.find((dataset) => dataset.id === selectedId);

  useEffect(() => {
    let active = true;
    async function update() {
      try {
        const response = await get<Dataset[]>("/api/datasets");
        if (!active) return;
        const items = response;
        setDatasets(items);
        setError("");
        setLoading(false);
        setSelectedId((current) =>
          items.some((dataset) => dataset.id === current)
            ? current
            : items[0]?.id || "",
        );
      } catch (reason) {
        if (active) {
          setError(t("apiError", { error: String(reason) }));
          setLoading(false);
        }
      }
    }
    void update();
    const timer = window.setInterval(() => void update(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refresh, t]);

  useEffect(() => {
    if (!selectedId || !loadDetails) return;
    const request = ++sequence.current;
    let active = true;
    let inFlight = false;
    let taskSnapshot = "";

    async function update() {
      if (inFlight) return;
      inFlight = true;
      const next = await loadDataset(selectedId, t);
      if (active && request === sequence.current) {
        taskSnapshot = JSON.stringify(next.tasks);
        setLoaded({ id: selectedId, data: next });
      }
      inFlight = false;
    }
    async function pollTasks() {
      if (inFlight) return;
      try {
        const tasks = (await get<Task[]>("/api/tasks")).filter(
          (task) => task.dataset_id === selectedId,
        );
        if (active && JSON.stringify(tasks) !== taskSnapshot) await update();
      } catch {
        // The workspace connection indicator reports an unavailable API.
      }
    }
    void update();
    const timer = window.setInterval(() => void pollTasks(), 5000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selectedId, refresh, t, loadDetails]);

  return {
    datasets,
    selectedId,
    setSelectedId,
    data,
    loading,
    error,
    setRefresh,
    selected,
  };
}
