import { useI18n } from "../i18n/useI18n";

import "./evidence-signatures.css";

export type TriStateValue = "present" | "absent" | "unknown" | null;
export function TriState({
  value,
  accepted = false,
}: {
  value: TriStateValue;
  accepted?: boolean;
}) {
  const { t } = useI18n();
  const labels = {
    present: "evPresent",
    absent: "evAbsent",
    unknown: "evUnknown",
    missing: "evMissingAssertion",
  } as const;
  return (
    <span
      className={`tri-state ${value ?? "missing"}${accepted ? " accepted" : ""}`}
      role="img"
      aria-label={t(labels[value ?? "missing"])}
    >
      {value === "present"
        ? t("evYes")
        : value === "absent"
          ? t("evNo")
          : value === "unknown"
            ? "?"
            : "·"}
      {accepted && <span aria-hidden="true">✓</span>}
    </span>
  );
}
