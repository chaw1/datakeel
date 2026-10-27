import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import type { DatasheetDocument } from "../../api/datasheets";
import type { components } from "../../api/generated";
import type { MessageKey } from "../../i18n/en";

type Comparison = components["schemas"]["DatasheetComparison"];
type Change = Comparison["changes"][number];

const visible = 40;
const kinds: Record<Change["kind"], MessageKey> = {
  added: "datasheetAdded",
  removed: "datasheetRemoved",
  changed: "datasheetChanged",
};

function shown(value: Change["before"]): string {
  if (value === null || value === undefined) return "—";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 160 ? `${text.slice(0, 159)}…` : text;
}

export function DatasheetChanges({
  before,
  after,
}: {
  before: DatasheetDocument;
  after: DatasheetDocument;
}) {
  const { t } = useI18n();
  const resource = useResource<Comparison>(
    `/api/datasheets/${encodeURIComponent(before.id)}/compare/${encodeURIComponent(after.id)}`,
  );
  const comparison = resource.value;
  const facts = new Map(
    [...before.facts, ...after.facts].map((fact) => [fact.id, fact]),
  );
  const titles = new Map(
    after.sections.map((section) => [section.key, section.title]),
  );
  return (
    <section className="datasheet-changes" aria-label={t("datasheetChanges")}>
      <h3>{t("datasheetChanges")}</h3>
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {comparison && !comparison.changes.length && (
        <p>{t("datasheetNoChanges")}</p>
      )}
      {comparison && !!comparison.changes.length && (
        <>
          <p>
            {t("datasheetChangedChapters", {
              chapters: comparison.changed_chapters
                .map((key) => titles.get(key) ?? key)
                .join(" · "),
            })}
          </p>
          <ul>
            {comparison.changes.slice(0, visible).map((change) => (
              <li key={`${change.kind}:${change.fact_id}`}>
                <span className="badge gray">{t(kinds[change.kind])}</span>{" "}
                <code>
                  {facts.get(change.fact_id)?.field ?? change.fact_id}
                </code>{" "}
                <span>{shown(change.before)}</span> →{" "}
                <span>{shown(change.after)}</span>
              </li>
            ))}
          </ul>
          {comparison.changes.length > visible && (
            <p className="muted">
              {t("datasheetMoreChanges", {
                count: comparison.changes.length - visible,
              })}
            </p>
          )}
        </>
      )}
    </section>
  );
}
