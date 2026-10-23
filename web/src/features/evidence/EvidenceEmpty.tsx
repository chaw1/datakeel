import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import { EvidenceExtraction } from "./EvidenceExtraction";
import { initialFilters } from "./query";

import type { EvidenceFilters } from "./query";
import type { Dataset } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";
import type { MessageKey } from "../../i18n/en";

export function EvidenceEmpty({
  datasetId,
  dataset,
  filters,
  onChange,
  unextracted = false,
  sourceVersion,
  onDataChanged,
  onComplete,
  onOpenReceipt,
}: {
  datasetId: string;
  dataset?: Dataset;
  filters: EvidenceFilters;
  onChange: (value: EvidenceFilters) => void;
  unextracted?: boolean;
  sourceVersion?: string;
  onDataChanged?: () => void;
  onComplete?: () => void;
  onOpenReceipt?: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const resource = useResource<Dataset>(
    dataset ? null : `/api/datasets/${encodeURIComponent(datasetId)}`,
  );
  const source = dataset ?? resource.value;
  const fields: [keyof EvidenceFilters, MessageKey][] = [
    ["concept", "evConcept"],
    ["scene", "evScene"],
    ["gap", "evGap"],
    ["split", "evSplit"],
    ["near", "evNear"],
    ["qualityMin", "evQualityMin"],
    ["qualityMax", "evQualityMax"],
  ];
  const conditions = fields.filter(
    ([key]) => filters[key] !== initialFilters[key],
  );
  const kind =
    source?.file_count === 0
      ? "data"
      : conditions.length && !unextracted
        ? "filtered"
        : "extraction";
  return (
    <section className="evidence-empty" data-empty-kind={kind}>
      <h3>
        {t(
          kind === "data"
            ? "evNoData"
            : kind === "filtered"
              ? "evFilteredEmpty"
              : "evNoExtraction",
        )}
      </h3>
      {kind === "filtered" ? (
        <ul>
          {conditions.map(([key, label]) => (
            <li key={key}>
              <span>
                {t(label)}: {String(filters[key])}
              </span>{" "}
              <button
                className="text-button"
                onClick={() => {
                  onChange({ ...filters, [key]: initialFilters[key] });
                }}
              >
                {t("evRemoveFilter", { condition: t(label) })}
              </button>
            </li>
          ))}
        </ul>
      ) : kind === "data" ? (
        <a className="button" href="#/datasets">
          {t("evAddData")}
        </a>
      ) : (
        <EvidenceExtraction
          key={`${datasetId}:${sourceVersion ?? ""}`}
          datasetId={datasetId}
          sourceVersion={sourceVersion}
          onDataChanged={onDataChanged}
          onComplete={onComplete}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </section>
  );
}
