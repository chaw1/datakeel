import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { CodeListEditor } from "./CodeListEditor";
import { StandardEditor } from "./StandardEditor";
import { sensitivityLabels, standardStatuses } from "./values";

import type { CodeList, FieldStandard } from "../../api/standards";
import type { LineageTarget } from "../../app/navigation";

export function StandardDetail({
  standard,
  codeList,
  onChanged,
  onOpenReceipt,
}: {
  standard?: FieldStandard;
  codeList?: CodeList;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const [editing, setEditing] = useState(false);
  const item = standard ?? codeList;
  if (!item) return null;
  return (
    <section
      className="catalog-detail"
      aria-label={t(standard ? "stdStandard" : "stdCodes")}
    >
      <div className="section-heading">
        <h2>
          {standard
            ? locale === "zh"
              ? standard.name_zh
              : standard.name_en
            : codeList?.name}
        </h2>
        <span className="badge">
          {t(
            standardStatuses.find(([value]) => value === item.status)?.[1] ??
              "stdDraft",
          )}
        </span>
      </div>
      <dl className="catalog-definition">
        <dt>{t("stdCode")}</dt>
        <dd>
          <code>{item.code}</code>
        </dd>
        <dt>{t("version")}</dt>
        <dd>{item.version}</dd>
        {standard && (
          <>
            <dt>{t("stdNameZh")}</dt>
            <dd>{standard.name_zh}</dd>
            <dt>{t("stdNameEn")}</dt>
            <dd>{standard.name_en}</dd>
            <dt>{t("stdDefinition")}</dt>
            <dd>{standard.description}</dd>
            <dt>{t("stdType")}</dt>
            <dd>{standard.data_type}</dd>
            <dt>{t("stdLength")}</dt>
            <dd>{standard.length ?? t("catNotSet")}</dd>
            <dt>{t("stdPrecision")}</dt>
            <dd>
              {standard.precision ?? "—"} / {standard.scale ?? "—"}
            </dd>
            <dt>{t("stdCodes")}</dt>
            <dd>{standard.code_list ?? t("catNotSet")}</dd>
            <dt>{t("stdRange")}</dt>
            <dd>
              {standard.minimum ?? "—"} – {standard.maximum ?? "—"}
            </dd>
            <dt>{t("stdPattern")}</dt>
            <dd>
              <code>{standard.pattern ?? "—"}</code>
            </dd>
            <dt>{t("stdUnit")}</dt>
            <dd>{standard.unit ?? t("catNotSet")}</dd>
            <dt>{t("stdRequired")}</dt>
            <dd>{t(standard.required ? "yes" : "no")}</dd>
            <dt>{t("stdSensitivity")}</dt>
            <dd>{t(sensitivityLabels[standard.sensitivity])}</dd>
            <dt>{t("stdOwner")}</dt>
            <dd>{standard.owner || t("catNotSet")}</dd>
            <dt>{t("stdAliases")}</dt>
            <dd>{standard.aliases.join(", ") || "—"}</dd>
          </>
        )}
      </dl>
      {codeList && (
        <div className="catalog-table-scroll">
          <table>
            <thead>
              <tr>
                <th>{t("stdValue")}</th>
                <th>{t("stdNameZh")}</th>
                <th>{t("stdNameEn")}</th>
              </tr>
            </thead>
            <tbody>
              {codeList.entries.map((entry) => (
                <tr key={`${typeof entry.value}:${String(entry.value)}`}>
                  <td>
                    <code>{String(entry.value)}</code>
                  </td>
                  <td>{entry.label_zh}</td>
                  <td>{entry.label_en}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <button
        className="button subtle"
        onClick={() => {
          setEditing(!editing);
        }}
      >
        {t("stdEdit")}
      </button>
      {editing && standard && (
        <StandardEditor
          definition={standard}
          onChanged={onChanged}
          onOpenReceipt={onOpenReceipt}
        />
      )}
      {editing && codeList && (
        <CodeListEditor
          definition={codeList}
          onChanged={onChanged}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </section>
  );
}
