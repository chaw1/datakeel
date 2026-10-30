import { useEffect, useState } from "react";

import { getTaskSamples } from "../../../api/production";
import { useI18n } from "../../../i18n/useI18n";
import { actionMessage } from "../actionErrors";
import { executeProduction, prepareProduction } from "../actions";

import { needsApproval, PlanSigner } from "./PlanSigner";

import type {
  PackageAcceptance,
  PackageSampling,
} from "../../../api/production";
import type { ActionPlan } from "../../../api/types";

interface Check {
  defective: boolean;
  reason: string;
}

/** Inspect every sampled unit, prepare the package decision, then sign it. */
export function PackageAcceptanceDialog({
  projectId,
  packageName,
  acceptance,
  sampling,
  onDone,
  onCancel,
}: {
  projectId: string;
  packageName: string;
  acceptance: PackageAcceptance;
  sampling: PackageSampling;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const [names, setNames] = useState<Record<string, string>>({});
  const [checks, setChecks] = useState<Record<string, Check>>({});
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    void getTaskSamples(projectId, sampling.task_ids).then(
      (result) => {
        setNames(
          Object.fromEntries(
            result.items.map((item) => [item.sample_id, item.name]),
          ),
        );
      },
      () => undefined,
    );
  }, [projectId, sampling.task_ids]);
  const check = (sample: string) =>
    checks[sample] ?? { defective: false, reason: "" };
  const defective = sampling.sample_ids.filter(
    (sample) => check(sample).defective,
  ).length;
  const accepted = defective <= sampling.acceptance_number;
  async function prepare() {
    if (
      sampling.sample_ids.some(
        (sample) => check(sample).defective && !check(sample).reason.trim(),
      )
    ) {
      setError(t("wbDefectReasonRequired"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      setPlan(
        await prepareProduction("accept_package", {
          package_id: acceptance.package_id,
          checks: sampling.sample_ids.map((sample) => ({
            sample_id: sample,
            defective: check(sample).defective,
            reason: check(sample).reason.trim(),
          })),
        }),
      );
    } catch (reason) {
      setError(actionMessage(reason, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  async function sign() {
    if (!plan) return;
    setBusy(true);
    setError("");
    try {
      await executeProduction(plan, needsApproval(plan));
      onDone();
    } catch (reason) {
      setPlan(null);
      setError(actionMessage(reason, t, t("wbError")));
    } finally {
      setBusy(false);
    }
  }
  const title = t("wbAcceptPackageTitle", { name: packageName });
  return (
    <section className="card wb-acceptance" aria-label={title}>
      <h3>{title}</h3>
      <p>
        {t("wbAcceptSampleRule", {
          sample: sampling.sample_size,
          lot: sampling.lot_size,
          allowed: sampling.acceptance_number,
        })}
      </p>
      <table aria-label={t("wbSampledTasks")}>
        <thead>
          <tr>
            <th>{t("wbSample")}</th>
            <th>{t("wbDefective")}</th>
            <th>{t("wbDefectReason")}</th>
          </tr>
        </thead>
        <tbody>
          {sampling.sample_ids.map((sample) => (
            <tr key={sample}>
              <td>{names[sample] ?? t("wbUnnamedSample")}</td>
              <td>
                <input
                  type="checkbox"
                  aria-label={t("wbMarkDefective", {
                    name: names[sample] ?? sample,
                  })}
                  checked={check(sample).defective}
                  disabled={busy || !!plan}
                  onChange={(event) => {
                    setChecks({
                      ...checks,
                      [sample]: {
                        ...check(sample),
                        defective: event.target.checked,
                      },
                    });
                  }}
                />
              </td>
              <td>
                <input
                  type="text"
                  aria-label={t("wbDefectReasonFor", {
                    name: names[sample] ?? sample,
                  })}
                  value={check(sample).reason}
                  disabled={busy || !!plan || !check(sample).defective}
                  onChange={(event) => {
                    setChecks({
                      ...checks,
                      [sample]: {
                        ...check(sample),
                        reason: event.target.value,
                      },
                    });
                  }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!plan ? (
        <div className="wb-plan-actions">
          <button type="button" disabled={busy} onClick={onCancel}>
            {t("wbCancel")}
          </button>
          <button
            type="button"
            className="button primary"
            disabled={busy}
            onClick={() => {
              void prepare();
            }}
          >
            {t("wbPrepareAcceptance")}
          </button>
        </div>
      ) : (
        <PlanSigner
          title={t("wbAcceptancePlan")}
          plan={plan}
          busy={busy}
          signLabel={t("wbSignAcceptance")}
          onCancel={() => {
            setPlan(null);
          }}
          onSign={() => {
            void sign();
          }}
        >
          <ul className="wb-plan-summary">
            <li>
              {t("wbAcceptPlanChecked", {
                sample: sampling.sample_size,
                defective,
                allowed: sampling.acceptance_number,
              })}
            </li>
            <li>
              {accepted
                ? t("wbAcceptPlanAccept")
                : t("wbAcceptPlanReject", { count: acceptance.total })}
            </li>
          </ul>
        </PlanSigner>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
