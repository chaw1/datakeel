import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { kindLabels, objectStatus } from "./descriptors";
import { objectHref } from "./navigation";

import type { ObjectTarget } from "./navigation";
import type { ObjectData } from "../../api/objects";

export function ObjectHeader({
  data,
  target,
}: {
  data: ObjectData;
  target: ObjectTarget;
}) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const chatDataset =
    target.kind === "dataset"
      ? target.id
      : (data.dataset?.id ?? target.datasetId);
  const chat = `#/agent?${new URLSearchParams({ prompt: t("objChatPrompt", { name: data.name, kind: t(kindLabels[target.kind]), id: target.id }), ...(chatDataset ? { dataset: chatDataset } : {}) }).toString()}`;
  const ask = `#/ask?${new URLSearchParams({ question: t("objAskPrompt", { name: data.name }), ...(target.kind === "metric" ? { metric: target.id } : {}) }).toString()}`;
  async function copyId() {
    try {
      await navigator.clipboard.writeText(target.id);
      setCopied(true);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }
  return (
    <header className="object-header">
      <div>
        <p className="object-kicker">
          <span>{t(kindLabels[target.kind])}</span>
          <span className="badge gray">{t(objectStatus(data))}</span>
        </p>
        <h1 className="page-title">{data.name}</h1>
        <button
          className="object-id"
          title={target.id}
          aria-label={t("objCopyId")}
          onClick={() => {
            void copyId();
          }}
        >
          <code>{target.id.slice(0, 8)}</code>
          <span>{t(copied ? "objCopied" : "objCopyId")}</span>
        </button>
        {failed && (
          <p role="alert" className="error-text">
            {t("objCopyFailed")}
          </p>
        )}
      </div>
      <div className="object-actions">
        {["dataset", "file", "table"].includes(target.kind) && (
          <a className="button" href={chat}>
            {t("objChat")}
          </a>
        )}
        {["metric", "term"].includes(target.kind) && (
          <a className="button" href={ask}>
            {t("objAsk")}
          </a>
        )}
        {target.kind === "dataset" && (
          <a
            className="button"
            href={objectHref({
              ...target,
              tab: "evidence",
              section: "create-version",
            })}
          >
            {t("objCreateVersion")}
          </a>
        )}
        {target.kind === "metric" && (
          <a
            className="button"
            href={objectHref({ ...target, tab: "evidence", section: "edit" })}
          >
            {t("objEdit")}
          </a>
        )}
        {["table", "column"].includes(target.kind) && (
          <a
            className="button"
            href={objectHref({
              ...target,
              tab: "relations",
              relation: "derived",
            })}
          >
            {t("objImpact")}
          </a>
        )}
        {target.kind === "action_run" && (
          <a
            className="button"
            href={objectHref({
              ...target,
              tab: "history",
              eventId: data.action?.receipt?.event_id,
            })}
          >
            {t("objReceipt")}
          </a>
        )}
        {data.version && (
          <a
            className="button"
            href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(data.version.manifest, null, 2))}`}
            download={`manifest-${target.id}.json`}
          >
            {t("objExport")}
          </a>
        )}
      </div>
    </header>
  );
}
