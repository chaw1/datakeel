import { useI18n } from "../../i18n/useI18n";

import { exampleFilters, initialFilters } from "./query";

import type { EvidenceFilters as Filters } from "./query";
import type { MessageKey } from "../../i18n/en";

const states: [string, MessageKey][] = [
  ["present", "evPresent"],
  ["unknown", "evUnknown"],
  ["absent", "evAbsent"],
];
const fields: {
  key: Exclude<keyof Filters, "qualityMin" | "qualityMax" | "sort">;
  label: MessageKey;
  options: [string, MessageKey][];
}[] = [
  {
    key: "concept",
    label: "evConcept",
    options: [
      ["", "evAny"],
      ["person", "evPerson"],
      ["car", "evCar"],
    ],
  },
  { key: "presence", label: "evPresence", options: states },
  {
    key: "scene",
    label: "evScene",
    options: [
      ["", "evAny"],
      ["night", "evNight"],
      ["rain", "evRain"],
      ["indoor", "evIndoor"],
    ],
  },
  { key: "sceneState", label: "evSceneState", options: states },
  {
    key: "gap",
    label: "evGap",
    options: [
      ["", "evAny"],
      ["missing", "evMissingLabel"],
      ["present", "evGapPresent"],
      ["unknown", "evGapUnknown"],
    ],
  },
  {
    key: "split",
    label: "evSplit",
    options: [
      ["", "evAny"],
      ["train", "evTrain"],
      ["val", "evVal"],
    ],
  },
  {
    key: "near",
    label: "evNear",
    options: [
      ["", "evAny"],
      ["train", "evTrain"],
      ["val", "evVal"],
    ],
  },
];
export function EvidenceFilters({
  value,
  onChange,
}: {
  value: Filters;
  onChange: (value: Filters) => void;
}) {
  const { t } = useI18n();
  return (
    <section className="evidence-filter-card" aria-label={t("evFilters")}>
      <div className="evidence-filter-toolbar">
        <div className="evidence-filter-actions">
          <button
            className="text-button"
            onClick={() => {
              onChange(exampleFilters);
            }}
          >
            {t("evExample")}
          </button>
          <button
            className="text-button"
            onClick={() => {
              onChange(initialFilters);
            }}
          >
            {t("evReset")}
          </button>
        </div>
        <label className="evidence-sort">
          {t("evSort")}
          <select
            value={value.sort}
            onBlur={(event) => {
              if (value.sort !== event.target.value)
                onChange({
                  ...value,
                  sort: event.target.value as Filters["sort"],
                });
            }}
            onChange={(event) => {
              onChange({
                ...value,
                sort: event.target.value as Filters["sort"],
              });
            }}
          >
            <option value="review">{t("evSortReview")}</option>
            <option value="filename">{t("evSortFilename")}</option>
            <option value="quality">{t("evSortQuality")}</option>
          </select>
        </label>
      </div>
      <details className="evidence-filter-panel">
        <summary>{t("evFilters")}</summary>
        <div className="evidence-filters">
          {fields.map((field) => (
            <label key={field.key}>
              <span>{t(field.label)}</span>
              <select
                value={value[field.key]}
                onBlur={(event) => {
                  if (value[field.key] !== event.target.value)
                    onChange({ ...value, [field.key]: event.target.value });
                }}
                onChange={(event) => {
                  onChange({ ...value, [field.key]: event.target.value });
                }}
              >
                {field.options.map(([id, label]) => (
                  <option key={id} value={id}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {(
            [
              ["qualityMin", "evQualityMin"],
              ["qualityMax", "evQualityMax"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              <span>{t(label)}</span>
              <input
                type="number"
                min={0}
                max={100}
                value={value[key]}
                onChange={(event) => {
                  onChange({
                    ...value,
                    [key]: Math.min(
                      100,
                      Math.max(0, Number(event.target.value)),
                    ),
                  });
                }}
              />
            </label>
          ))}
        </div>
      </details>
    </section>
  );
}
