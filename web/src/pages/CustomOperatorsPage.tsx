import { useState } from "react";

import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { ActionReceipt } from "../features/actions/ActionReceipt";
import { PlanCard } from "../features/actions/PlanCard";
import { CustomCodeApproval } from "../features/custom-operators/CustomCodeApproval";
import { OperatorRunHistory } from "../features/custom-operators/OperatorRunHistory";
import { OperatorVersionCard } from "../features/custom-operators/OperatorVersionCard";
import { SubmissionForm } from "../features/custom-operators/SubmissionForm";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type {
  CustomOperatorConfiguration,
  CustomOperatorRun,
  CustomOperatorVersion,
} from "../api/customOperators";
import type { ActionPlan, ActionRun, Dataset } from "../api/types";
import type { LineageTarget } from "../app/navigation";

export function CustomOperatorsPage({
  datasets,
  onDataChanged,
  onOpenReceipt,
}: {
  datasets: Dataset[];
  onDataChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const versions = useResource<CustomOperatorVersion[]>(
    "/api/custom-operators",
  );
  const submissions = useResource<ActionPlan[]>(
    "/api/custom-operators/submissions",
  );
  const runs = useResource<CustomOperatorRun[]>("/api/custom-operators/runs");
  const configuration = useResource<CustomOperatorConfiguration>(
    "/api/custom-operators/configuration",
  );
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [receipt, setReceipt] = useState<ActionRun | null>(null);
  const currentPlan = plan
    ? (submissions.value?.find((item) => item.id === plan.id) ??
      (submissions.loading || submissions.error ? plan : null))
    : null;
  const pendingPlan =
    currentPlan && ["PREPARED", "APPROVED"].includes(currentPlan.status)
      ? currentPlan
      : null;
  function reload() {
    versions.reload();
    submissions.reload();
    runs.reload();
    configuration.reload();
  }
  function changed() {
    reload();
    onDataChanged();
  }
  function prepared(next: ActionPlan) {
    setPlan(next);
    changed();
  }
  function resolved() {
    setPlan(null);
    changed();
  }
  return (
    <div className="custom-operators-page">
      <div className="page-heading">
        <div>
          <h1>{t("customOperatorsNav")}</h1>
          <p>{t("customOperatorsIntro")}</p>
        </div>
        <button className="button" onClick={reload}>
          <Icon name="refresh" />
          {t("refresh")}
        </button>
      </div>
      <ResourceState {...configuration} onRetry={configuration.reload} />
      {configuration.value && (
        <p className="muted">
          {t("customOperatorBackend")}:{" "}
          <strong>{configuration.value.backend}</strong> ·{" "}
          <code>{configuration.value.container_image}</code>
        </p>
      )}
      {configuration.value?.subprocess_enabled && (
        <div className="custom-unsafe-warning" role="alert">
          <strong>{t("customOperatorUnsafeTitle")}</strong>
          <p>{t("customOperatorUnsafe")}</p>
        </div>
      )}
      <SubmissionForm onPrepared={prepared} />
      {pendingPlan && (
        <section aria-label={t("customOperatorReview")}>
          <p role="status">{t("customOperatorReviewPending")}</p>
          <PlanCard
            key={`${pendingPlan.id}:${pendingPlan.plan_digest}:${pendingPlan.status}`}
            plan={pendingPlan}
            onResolved={resolved}
            onOpenReceipt={onOpenReceipt}
          />
        </section>
      )}
      <section aria-label={t("customOperatorSubmissions")}>
        <h2>{t("customOperatorSubmissions")}</h2>
        <ResourceState {...submissions} onRetry={submissions.reload} />
        {submissions.value &&
          (!submissions.value.length ? (
            <p className="muted">{t("customOperatorNoSubmissions")}</p>
          ) : (
            <ul className="custom-submissions">
              {submissions.value.map((item) => (
                <li key={item.id}>
                  <code>
                    {typeof item.canonical_params.name === "string"
                      ? item.canonical_params.name
                      : item.id}
                  </code>
                  <span>{t(item.status)}</span>
                  <code className="custom-hash">
                    {typeof item.canonical_params.code_hash === "string"
                      ? item.canonical_params.code_hash
                      : ""}
                  </code>
                  {item.status === "PREPARED" && (
                    <a
                      href={`#/approvals?${new URLSearchParams({ plan: item.id }).toString()}`}
                    >
                      {t("customOperatorOpenApproval")}
                    </a>
                  )}
                  {item.status === "APPROVED" && (
                    <button
                      className="text-button"
                      type="button"
                      onClick={() => {
                        setPlan(item);
                      }}
                    >
                      {t("customOperatorOpenApproval")}
                    </button>
                  )}
                  <details>
                    <summary>{t("customOperatorReview")}</summary>
                    <CustomCodeApproval plan={item} />
                  </details>
                </li>
              ))}
            </ul>
          ))}
      </section>
      <section aria-label={t("customOperatorVersions")}>
        <h2>{t("customOperatorVersions")}</h2>
        <ResourceState {...versions} onRetry={versions.reload} />
        {versions.value &&
          (!versions.value.length ? (
            <p className="muted">{t("customOperatorNoVersions")}</p>
          ) : (
            <div className="custom-versions">
              {versions.value.map((item) => (
                <OperatorVersionCard
                  key={item.id}
                  version={item}
                  datasets={datasets}
                  blocked={
                    !configuration.value ||
                    configuration.value.backend === "subprocess"
                  }
                  onQueued={(run) => {
                    setReceipt(run);
                    changed();
                  }}
                />
              ))}
            </div>
          ))}
      </section>
      {receipt && (
        <>
          <p role="status">{t("customOperatorRunQueued")}</p>
          <ActionReceipt run={receipt} onOpenReceipt={onOpenReceipt} />
        </>
      )}
      <ResourceState {...runs} onRetry={runs.reload} />
      {runs.value && <OperatorRunHistory runs={runs.value} />}
    </div>
  );
}
