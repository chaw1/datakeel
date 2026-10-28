import { useState } from "react";

import { standardsPath } from "../../api/standards";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useResource } from "../../lib/useResource";

import { CodeListEditor } from "./CodeListEditor";
import { StandardDetail } from "./StandardDetail";
import { StandardEditor } from "./StandardEditor";
import { standardStatuses } from "./values";

import type { CodeList, FieldStandard } from "../../api/standards";
import type { LineageTarget } from "../../app/navigation";

export function StandardsBrowser({
  collection,
  onChanged,
  onOpenReceipt,
}: {
  collection: "fields" | "code-lists";
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState("");
  const [creating, setCreating] = useState(false);
  const fields = useResource<FieldStandard[]>(
    collection === "fields" ? standardsPath(collection, search, status) : null,
  );
  const codes = useResource<CodeList[]>(
    collection === "code-lists"
      ? standardsPath(collection, search, status)
      : null,
  );
  const resource = collection === "fields" ? fields : codes;
  const items = resource.value ?? [];
  const standard = fields.value?.find((item) => item.code === selected);
  const codeList = codes.value?.find((item) => item.code === selected);
  return (
    <div className="standards-section card">
      <div className="standards-toolbar">
        <label>
          {t("stdSearch")}
          <input
            type="search"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </label>
        <label>
          {t("stdStatus")}
          <select
            value={status}
            onBlur={(event) => {
              setStatus(event.target.value);
            }}
            onChange={(event) => {
              setStatus(event.target.value);
            }}
          >
            <option value="">{t("stdAll")}</option>
            {standardStatuses.map(([value, label]) => (
              <option key={value} value={value}>
                {t(label)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        className="button subtle"
        onClick={() => {
          setCreating(!creating);
        }}
      >
        {t(collection === "fields" ? "stdCreateField" : "stdCreateCodeList")}
      </button>
      {creating &&
        (collection === "fields" ? (
          <StandardEditor
            definition={{
              code: "",
              name_zh: "",
              name_en: "",
              description: "",
              data_type: "string",
              required: false,
              sensitivity: "internal",
              owner: "",
              aliases: [],
              version: 1,
              status: "draft",
            }}
            onChanged={onChanged}
            onOpenReceipt={onOpenReceipt}
          />
        ) : (
          <CodeListEditor
            definition={{
              code: "",
              name: "",
              entries: [],
              version: 1,
              status: "draft",
            }}
            onChanged={onChanged}
            onOpenReceipt={onOpenReceipt}
          />
        ))}
      <ResourceState
        loading={resource.loading}
        error={resource.error}
        onRetry={resource.reload}
      />
      {!resource.loading && !resource.error && (
        <div className="catalog-browser">
          <ul className="catalog-object-list">
            {items.map((item) => (
              <li key={item.code}>
                <button
                  className={selected === item.code ? "selected" : ""}
                  onClick={() => {
                    setSelected(item.code);
                  }}
                >
                  <strong>
                    {"name_zh" in item
                      ? locale === "zh"
                        ? item.name_zh
                        : item.name_en
                      : item.name}
                  </strong>
                  <span>
                    {item.code} ·{" "}
                    {t(
                      standardStatuses.find(
                        ([value]) => value === item.status,
                      )?.[1] ?? "stdDraft",
                    )}
                  </span>
                </button>
              </li>
            ))}
            {!items.length && <li>{t("stdEmpty")}</li>}
          </ul>
          {standard || codeList ? (
            <StandardDetail
              key={selected}
              standard={standard}
              codeList={codeList}
              onChanged={onChanged}
              onOpenReceipt={onOpenReceipt}
            />
          ) : (
            <p className="empty-state">{t("stdChoose")}</p>
          )}
        </div>
      )}
    </div>
  );
}
