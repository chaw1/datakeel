import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { actionMessage } from "./actionErrors";
import { executeProduction, prepareProduction } from "./actions";
import { needsApproval, PlanSigner } from "./team/PlanSigner";
import {
  TemplateUpgradeSummary,
  upgradeDetails,
} from "./TemplateUpgradeSummary";

import type { ProjectWorkbench } from "../../api/production";
import type { ActionPlan } from "../../api/types";

/** Versions this project is locked to, against the newest ones it could be upgraded to. */
export function templateVersions(data: ProjectWorkbench) {
  const current = data.template?.revision ?? null;
  const latest = data.latest_template ?? data.template;
  const labels = data.label_set.version;
  const latestLabels = Math.max(
    data.latest_label_set_version ?? labels,
    labels,
  );
  const newerTemplate =
    current !== null &&
    latest !== null &&
    !latest.archived &&
    latest.revision > current;
  return {
    current,
    latest: latest?.revision ?? null,
    labels,
    latestLabels,
    newer: newerTemplate || latestLabels > labels,
  };
}

/**
 * The cockpit card for R1: "current template vN, latest vM", and for a manager an upgrade
 * that is prepared as a plan, read in plain words and signed before anything changes.
 */
export function TemplateVersions({
  data,
  canUpgrade,
  onChanged,
}: {
  data: ProjectWorkbench;
  canUpgrade: boolean;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const versions = templateVersions(data);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<number | null>(null);
  if (versions.current === null && !versions.newer) return null;
  async function run(step: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await step();
    } catch (reason) {
      setPlan(null);
      setError(actionMessage(reason, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  const prepare = () =>
    run(async () => {
      setDone(null);
      setPlan(
        await prepareProduction("upgrade_project_template", {
          project_id: data.project.id,
        }),
      );
    });
  const sign = (signed: ActionPlan) =>
    run(async () => {
      await executeProduction(signed, needsApproval(signed));
      setDone(upgradeDetails(signed)?.to_template_version ?? versions.latest);
      setPlan(null);
      onChanged();
    });
  const finalized = !!data.project.finalized_version_id;
  const sampleName = (id: string) => {
    const sample = data.task_samples.find((item) => item.task_id === id);
    return sample ? sample.path || sample.name : id;
  };
  return (
    <section
      className="card wb-template-versions"
      aria-label={t("wbTemplateLock")}
    >
      <h2>{t("wbTemplateLock")}</h2>
      {versions.current !== null && (
        <p>
          {t("wbTemplateLockCurrent", {
            current: versions.current,
            latest: versions.latest ?? versions.current,
          })}
        </p>
      )}
      <p>
        {t("wbTemplateLockLabels", {
          current: versions.labels,
          latest: versions.latestLabels,
        })}
      </p>
      <p className="muted">
        {versions.newer
          ? t("wbTemplateLockNewer", { current: versions.current ?? "-" })
          : t("wbTemplateLockUpToDate")}
      </p>
      {versions.newer && canUpgrade && !finalized && !plan && (
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            void prepare();
          }}
        >
          {t("wbTemplateUpgrade")}
        </button>
      )}
      {plan && (
        <PlanSigner
          title={t("wbTemplateUpgradeTitle")}
          plan={plan}
          signLabel={t("wbTemplateUpgradeSign")}
          busy={busy}
          onSign={() => {
            void sign(plan);
          }}
          onCancel={() => {
            setPlan(null);
          }}
        >
          <TemplateUpgradeSummary plan={plan} name={sampleName} />
        </PlanSigner>
      )}
      {done !== null && (
        <p role="status">{t("wbTemplateUpgraded", { version: done })}</p>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
