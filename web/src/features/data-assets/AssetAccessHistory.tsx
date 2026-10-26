import { assetPath, scopeLabels } from "../../api/dataAssets";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { useClock } from "../../lib/useClock";
import { useResource } from "../../lib/useResource";

import { AssetPlanFeedback } from "./AssetPlanFeedback";
import { useAssetAction } from "./useAssetAction";

import type { AssetApplication, AssetGrant } from "../../api/dataAssets";
import type { LineageTarget } from "../../app/navigation";

const statuses = {
  pending: "assetPending",
  approved: "assetApproved",
  rejected: "assetRejected",
} as const;

export function AssetAccessHistory({
  assetId,
  onChanged,
  onOpenReceipt,
}: {
  assetId: string;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const now = useClock();
  const applications = useResource<AssetApplication[]>(
    `${assetPath(assetId)}/applications`,
  );
  const grants = useResource<AssetGrant[]>(
    `/api/data-assets/grants?${new URLSearchParams({ asset_id: assetId }).toString()}`,
  );
  function changed() {
    applications.reload();
    grants.reload();
    onChanged();
  }
  const action = useAssetAction(changed);
  return (
    <section className="asset-section">
      <h2>{t("assetApplications")}</h2>
      <ResourceState {...applications} onRetry={applications.reload} />
      {applications.value?.length === 0 && (
        <p className="muted">{t("assetNoApplications")}</p>
      )}
      {applications.value?.map((item) => (
        <article className="asset-request" key={item.id}>
          <div className="asset-title-row">
            <strong>{item.applicant}</strong>
            <span className="badge">{t(statuses[item.status])}</span>
          </div>
          <p>{item.purpose}</p>
          <p>
            {item.scopes.map((scope) => t(scopeLabels[scope])).join(" · ")} ·{" "}
            {t("assetExpires")}: {date(item.expires_at, locale)}
          </p>
          <p className="mono">{item.id}</p>
          {item.decided_by && (
            <p>
              {t("assetDecisionBy")}: {item.decided_by}
            </p>
          )}
          {item.grant_id && (
            <p>
              {t("assetGrantId")}: <span className="mono">{item.grant_id}</span>
            </p>
          )}
          {item.status === "pending" && (
            <div className="asset-controls">
              {([true, false] as const).map((approve) => (
                <button
                  className="button"
                  key={String(approve)}
                  disabled={action.busy}
                  onKeyDown={(event) => {
                    if (action.isComposing(event.nativeEvent))
                      event.preventDefault();
                  }}
                  onClick={() => {
                    void action.prepare("decide_asset_application", {
                      application_id: item.id,
                      approve,
                      reason: "",
                    });
                  }}
                >
                  {t(approve ? "assetApprove" : "assetReject")}
                </button>
              ))}
            </div>
          )}
        </article>
      ))}
      <h2>{t("assetGrants")}</h2>
      <ResourceState {...grants} onRetry={grants.reload} />
      {grants.value?.length === 0 && (
        <p className="muted">{t("assetNoGrants")}</p>
      )}
      {grants.value?.map((grant) => {
        const state = grant.revoked_at
          ? "assetRevoked"
          : new Date(grant.expires_at).getTime() <= now
            ? "assetExpired"
            : "assetActive";
        return (
          <article className="asset-request" key={grant.id}>
            <div className="asset-title-row">
              <strong>{grant.subject}</strong>
              <span className="badge">{t(state)}</span>
            </div>
            <p className="mono">{grant.id}</p>
            <p>
              {grant.scopes.map((scope) => t(scopeLabels[scope])).join(" · ")} ·{" "}
              {t("assetExpires")}: {date(grant.expires_at, locale)}
            </p>
            {state === "assetActive" && (
              <button
                className="button"
                disabled={action.busy}
                onKeyDown={(event) => {
                  if (action.isComposing(event.nativeEvent))
                    event.preventDefault();
                }}
                onClick={() => {
                  void action.prepare("revoke_asset_grant", {
                    grant_id: grant.id,
                    reason: "",
                  });
                }}
              >
                {t("assetRevoke")}
              </button>
            )}
          </article>
        );
      })}
      <AssetPlanFeedback
        action={action}
        onChanged={changed}
        onOpenReceipt={onOpenReceipt}
      />
    </section>
  );
}
