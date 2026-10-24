import { useState } from "react";

import { decideRelations } from "../../api/kg";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";

import { KGLinkTable } from "./KGLinkTable";
import { statusLabels } from "./labels";

import type { EntityLink } from "../../api/kg";

export function KGAssetLinks({
  datasetId,
  entityId,
  onChanged,
}: {
  datasetId?: string;
  entityId?: string;
  onChanged?: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [status, setStatus] = useState("");
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const query = new URLSearchParams(datasetId ? { dataset_id: datasetId } : {});
  const resource = useResource<EntityLink[]>(
    entityId
      ? `/api/kg/entities/${encodeURIComponent(entityId)}/links`
      : `/api/kg/links?${query.toString()}`,
  );
  const links = (resource.value ?? []).filter(
    (link) =>
      (!status || link.assertion.status === status) &&
      `${link.entity.name} ${link.target.name} ${link.target.asset_ref.asset_id}`
        .toLocaleLowerCase()
        .includes(name.toLocaleLowerCase()),
  );
  async function decide(ids: string[], next: "accepted" | "rejected") {
    if (busy || !ids.length || isComposing()) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const result = await decideRelations(ids, next, t("kgLinkReviewReason"));
      if (result.status !== "SUCCEEDED")
        throw new Error(result.error || t("evActionFailed"));
      setSelected([]);
      setSaved(true);
      resource.reload();
      onChanged?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="kg-asset-links" aria-label={t("kgAssetLinks")}>
      <h3>{t("kgAssetLinks")}</h3>
      <p className="muted">{t("kgLinkHint")}</p>
      <p className="muted">{t("kgLinkLatest")}</p>
      <div className="kg-filters">
        <label>
          {t("kgName")}
          <input
            type="search"
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              setSelected([]);
            }}
          />
        </label>
        <label>
          {t("kgStatus")}
          <select
            value={status}
            onBlur={(event) => {
              setStatus(event.target.value);
              setSelected([]);
            }}
            onChange={(event) => {
              setStatus(event.target.value);
              setSelected([]);
            }}
          >
            <option value="">{t("kgAllStatuses")}</option>
            {(["candidate", "accepted", "rejected"] as const).map((value) => (
              <option key={value} value={value}>
                {t(statusLabels[value])}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {saved && <p role="status">{t("kgReviewSaved")}</p>}
      <div className="kg-selection">
        <strong>{t("kgSelected", { count: selected.length })}</strong>
        <span>{t("kgLinkCount", { count: links.length })}</span>
        <button
          type="button"
          className="button"
          disabled={!selected.length || busy || resource.loading}
          onKeyDown={(event) => {
            if (isComposing(event.nativeEvent)) event.preventDefault();
          }}
          onClick={() => {
            void decide(selected, "accepted");
          }}
        >
          {t("kgAccept")}
        </button>
        <button
          type="button"
          className="button danger"
          disabled={!selected.length || busy || resource.loading}
          onKeyDown={(event) => {
            if (isComposing(event.nativeEvent)) event.preventDefault();
          }}
          onClick={() => {
            void decide(selected, "rejected");
          }}
        >
          {t("kgReject")}
        </button>
      </div>
      {links.length > 0 && (
        <KGLinkTable
          links={links}
          selected={selected}
          busy={busy || resource.loading}
          onSelect={setSelected}
          onDecide={(ids, next) => {
            void decide(ids, next);
          }}
        />
      )}
      {!resource.loading && !resource.error && !links.length && (
        <p>{t("kgLinkEmpty")}</p>
      )}
    </section>
  );
}
