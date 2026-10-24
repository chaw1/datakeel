import { useI18n } from "../../i18n/useI18n";

import { statusLabels } from "./labels";

import type { KGQuery } from "../../api/kg";

export function KGFilters({
  value,
  types,
  onChange,
}: {
  value: KGQuery;
  types: string[];
  onChange: (query: KGQuery) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="kg-filters">
      <label>
        {t("kgName")}
        <input
          type="search"
          value={value.name ?? ""}
          onChange={(event) => {
            onChange({ ...value, name: event.target.value || null });
          }}
        />
      </label>
      <label>
        {t("kgType")}
        <select
          aria-label={t("kgType")}
          value={value.entity_type ?? ""}
          onBlur={(event) => {
            onChange({ ...value, entity_type: event.target.value || null });
          }}
          onChange={(event) => {
            onChange({ ...value, entity_type: event.target.value || null });
          }}
        >
          <option value="">{t("kgAllTypes")}</option>
          {types.map((type) => (
            <option key={type}>{type}</option>
          ))}
        </select>
      </label>
      <label>
        {t("kgStatus")}
        <select
          aria-label={t("kgStatus")}
          value={value.status ?? ""}
          onBlur={(event) => {
            onChange({
              ...value,
              status: (event.target.value || null) as KGQuery["status"],
            });
          }}
          onChange={(event) => {
            onChange({
              ...value,
              status: (event.target.value || null) as KGQuery["status"],
            });
          }}
        >
          <option value="">{t("kgAllStatuses")}</option>
          {(["candidate", "accepted", "rejected"] as const).map((status) => (
            <option key={status} value={status}>
              {t(statusLabels[status])}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("kgVerification")}
        <select
          aria-label={t("kgVerification")}
          value={value.verification ?? ""}
          onBlur={(event) => {
            onChange({
              ...value,
              verification: (event.target.value ||
                null) as KGQuery["verification"],
            });
          }}
          onChange={(event) => {
            onChange({
              ...value,
              verification: (event.target.value ||
                null) as KGQuery["verification"],
            });
          }}
        >
          <option value="">{t("kgAllChecks")}</option>
          {(["needs_review", "verified"] as const).map((status) => (
            <option key={status} value={status}>
              {t(statusLabels[status])}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
