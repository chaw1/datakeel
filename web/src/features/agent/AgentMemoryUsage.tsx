import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import type { MemoryEntry } from "../../api/types";

export function AgentMemoryUsage({ ids }: { ids: string[] }) {
  const { t } = useI18n();
  const memories = useResource<MemoryEntry[]>(
    ids.length ? "/api/agent/memories" : null,
  );
  if (!ids.length) return null;
  return (
    <aside className="agent-memory" aria-label={t("memoryUsed")}>
      <strong>{t("memoryUsed")}</strong>
      {memories.error && <p>{t("memoryUnavailable")}</p>}
      <ul>
        {ids.map((id) => (
          <li key={id} data-used-memory-id={id}>
            {memories.value?.find((entry) => entry.id === id)?.content ??
              (memories.loading
                ? t("loadingData")
                : memories.error
                  ? id
                  : t("memoryDeletedReference", { id }))}
          </li>
        ))}
      </ul>
      <a href="#/memory">{t("memoryOpen")}</a>
    </aside>
  );
}
