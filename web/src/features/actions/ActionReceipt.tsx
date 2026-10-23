import { lineageHref } from "../../app/lineageNavigation";
import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";
import { StateBadge } from "../tasks/StateBadge";

import type { ActionRun } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function ActionReceipt({
  run,
  onOpenReceipt,
}: {
  run: ActionRun;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t, locale } = useI18n();
  const unsuccessful = run.status === "FAILED" || run.status === "DENIED";
  const reason = run.reason ?? run.error;
  const receipt = run.receipt;
  const refs = [...(receipt?.outputs ?? []), ...(receipt?.inputs ?? [])];
  const dataset = refs.find((ref) => ref.asset_type === "dataset");
  const asset =
    refs.find((ref) => ref.asset_type === "action_run") ??
    refs.find((ref) => ref.asset_type !== "dataset") ??
    dataset;
  const target: LineageTarget = {
    datasetId: dataset?.asset_id,
    assetId: asset?.asset_id,
    eventId: receipt?.event_id,
  };

  return (
    <section
      className={`action-receipt ${unsuccessful ? "receipt-failed" : ""}`}
      aria-label={t("receipt")}
    >
      <div className="receipt-heading">
        <Icon name={unsuccessful ? "close" : "check"} />
        <strong>{run.action_type}</strong>
        <StateBadge state={run.status} />
      </div>
      <dl className="detail-grid">
        <div>
          <dt>{t("runId")}</dt>
          <dd className="mono">{run.id}</dd>
        </div>
        <div>
          <dt>{t("createdAt")}</dt>
          <dd>{date(run.created_at, locale)}</dd>
        </div>
        {receipt && (
          <div>
            <dt>{t("performedBy")}</dt>
            <dd>{receipt.on_behalf_of}</dd>
          </div>
        )}
      </dl>
      {reason && <p className="error-text">{reason}</p>}
      {receipt && asset && (
        <a
          className="text-button"
          href={lineageHref(target)}
          onClick={(event) => {
            if (
              event.metaKey ||
              event.ctrlKey ||
              event.shiftKey ||
              event.altKey
            )
              return;
            event.preventDefault();
            onOpenReceipt(target);
          }}
        >
          {t("viewReceipt")}
          <Icon name="arrow" size={15} />
        </a>
      )}
      {!receipt && (run.status === "QUEUED" || run.status === "RUNNING") && (
        <p>{t("executionQueued")}</p>
      )}
    </section>
  );
}
