import { useState } from "react";

import { ResourceState } from "../components/ResourceState";
import { Button, PageHeader, Select } from "../components/ui";
import { MemoryForm } from "../features/memory/MemoryForm";
import { MemoryList } from "../features/memory/MemoryList";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { Dataset, MemoryEntry } from "../api/types";

export function MemoryPage({ datasets }: { datasets: Dataset[] }) {
  const { t } = useI18n();
  const [scope, setScope] = useState("all");
  const memories = useResource<MemoryEntry[]>("/api/agent/memories");
  const entries = (memories.value ?? []).filter(
    (entry) => scope === "all" || (entry.dataset_id ?? "global") === scope,
  );
  return (
    <>
      <PageHeader
        title={t("pageCount", { name: t("memoryNav"), count: entries.length })}
        subtitle={t("memoryDescription")}
        actions={
          <Button icon="refresh" onClick={memories.reload}>
            {t("refresh")}
          </Button>
        }
      />
      <div className="memory-layout">
        <MemoryForm datasets={datasets} onSaved={memories.reload} />
        <section aria-label={t("memoryNav")}>
          <div className="memory-filter">
            <label htmlFor="memory-filter">{t("memoryFilter")}</label>
            <Select
              id="memory-filter"
              onBlur={(event) => {
                setScope(event.target.value);
              }}
              value={scope}
              onChange={(event) => {
                setScope(event.target.value);
              }}
            >
              <option value="all">{t("memoryAllScopes")}</option>
              <option value="global">{t("memoryGlobal")}</option>
              {datasets.map((dataset) => (
                <option key={dataset.id} value={dataset.id}>
                  {dataset.name}
                </option>
              ))}
            </Select>
          </div>
          <ResourceState {...memories} onRetry={memories.reload} />
          {memories.value && (
            <MemoryList
              entries={entries}
              datasets={datasets}
              onDeleted={memories.reload}
            />
          )}
        </section>
      </div>
    </>
  );
}
