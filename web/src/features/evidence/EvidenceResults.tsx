import { Footnotes } from "../../components/Footnotes";
import { useI18n } from "../../i18n/useI18n";
import { objectHref } from "../object/navigation";

import { EvidenceRow } from "./EvidenceRow";
import { evidenceSources } from "./matrix";

import type { EvidenceSample } from "../../api/types";

export function EvidenceResults({
  items,
  selected,
  onSelect,
  onInspect,
  showFootnotes = true,
}: {
  items: EvidenceSample[];
  selected: EvidenceSample[];
  onSelect: (samples: EvidenceSample[]) => void;
  onInspect: (sample: EvidenceSample) => void;
  showFootnotes?: boolean;
}) {
  const { t } = useI18n();
  const ids = new Set(selected.map((item) => item.asset_ref.asset_id));
  const allSelected =
    items.length > 0 && items.every((item) => ids.has(item.asset_ref.asset_id));
  const sources = evidenceSources(items);
  const first = items[0];
  const common = items.every(
    (item) => item.source_version === first.source_version,
  );
  return (
    <>
      <div className="evidence-table-scroll">
        <table className="evidence-table" aria-label={t("evResults")}>
          {common && (
            <caption className="evidence-source-version">
              {t("evVersion")}:{" "}
              <a
                href={objectHref({
                  kind: "version",
                  id: first.source_version,
                  datasetId: first.dataset_id,
                  tab: "facts",
                })}
              >
                <code>{first.source_version}</code>
              </a>
            </caption>
          )}
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  aria-label={t("evSelectPage")}
                  checked={allSelected}
                  onChange={() => {
                    onSelect(allSelected ? [] : items);
                  }}
                />
              </th>
              <th>{t("evSample")}</th>
              <th>{t("evCaption")}</th>
              <th>{t("evAssertions")}</th>
              <th>{t("evQuality")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((sample) => (
              <EvidenceRow
                key={sample.asset_ref.asset_id}
                sample={sample}
                selected={ids.has(sample.asset_ref.asset_id)}
                sources={sources}
                commonVersion={common}
                onInspect={() => {
                  onInspect(sample);
                }}
                onSelect={() => {
                  onSelect(
                    ids.has(sample.asset_ref.asset_id)
                      ? selected.filter(
                          (item) =>
                            item.asset_ref.asset_id !==
                            sample.asset_ref.asset_id,
                        )
                      : [...selected, sample],
                  );
                }}
              />
            ))}
          </tbody>
        </table>
      </div>
      {showFootnotes && <Footnotes items={sources} />}
    </>
  );
}
