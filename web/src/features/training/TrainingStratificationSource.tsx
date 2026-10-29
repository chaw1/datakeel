import { useI18n } from "../../i18n/useI18n";

import type { SplitRequest } from "../../api/training";

const choices = ["all", "classification", "detection", "spans"] as const;
const labels = {
  all: "trainingStratificationAll",
  classification: "trainingStratificationClassification",
  detection: "trainingStratificationDetection",
  spans: "trainingStratificationSpans",
} as const;

export function TrainingStratificationSource({
  value,
  disabled,
  onChange,
}: {
  value: SplitRequest["stratification_source"];
  disabled: boolean;
  onChange: (value: SplitRequest["stratification_source"]) => void;
}) {
  const { t } = useI18n();
  return (
    <label>
      {t("trainingStratificationSource")}
      <select
        aria-label={t("trainingStratificationSource")}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(
            choices.find((choice) => choice === event.target.value) ?? "all",
          );
        }}
        onBlur={(event) => {
          onChange(
            choices.find((choice) => choice === event.target.value) ?? "all",
          );
        }}
      >
        {choices.map((choice) => (
          <option key={choice} value={choice}>
            {t(labels[choice])}
          </option>
        ))}
      </select>
    </label>
  );
}
