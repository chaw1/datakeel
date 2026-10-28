import { useState } from "react";

import { post } from "../../api/client";
import { useI18n } from "../../i18n/useI18n";
import { PlanCard } from "../actions/PlanCard";
import { objectHref } from "../object/navigation";

import type { InspectionCheck, SamplingPlan } from "../../api/annotation";
import type { components } from "../../api/generated";
import type { ActionPlan } from "../../api/types";

export function AnnotationInspection({
  sample,
  onChanged,
}: {
  sample: SamplingPlan;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [checks, setChecks] = useState<
    Partial<Record<string, InspectionCheck>>
  >({});
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const complete = sample.sample_ids.every(
    (id) => checks[id] && (!checks[id].defective || !!checks[id].reason.trim()),
  );
  function update(id: string, change: Partial<InspectionCheck>) {
    setChecks((previous) => ({
      ...previous,
      [id]: {
        ...(previous[id] ?? { sample_id: id, defective: false, reason: "" }),
        ...change,
      },
    }));
  }
  async function prepare() {
    if (!complete || busy) return;
    setBusy(true);
    setError("");
    try {
      const body: components["schemas"]["AnnotationAcceptanceParams"] = {
        dataset_id: sample.dataset_id,
        version_id: sample.version_id,
        batch_id: sample.batch_id,
        sampling_id: sample.id,
        checks: sample.sample_ids.flatMap((id) => {
          const check = checks[id];
          return check ? [check] : [];
        }),
      };
      setPlan(
        await post<ActionPlan>(
          "/api/actions/annotation_acceptance/prepare",
          body,
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <p>
        {t("annotationSampleSize")}: {sample.sample_size} ·{" "}
        {t("annotationAcRe")}: {sample.acceptance_number} /{" "}
        {sample.rejection_number} · {t("annotationSeed")}: {sample.seed}
      </p>
      <p>{t("annotationReviewSample")}</p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("annotationSample")}</th>
              <th>{t("annotationDecision")}</th>
              <th>{t("annotationDefectReason")}</th>
            </tr>
          </thead>
          <tbody>
            {sample.sample_ids.map((id) => (
              <tr key={id}>
                <td>
                  <code>{id}</code>
                </td>
                <td>
                  <select
                    aria-label={`${t("annotationDecision")} ${id}`}
                    disabled={!!plan}
                    value={
                      checks[id]
                        ? checks[id].defective
                          ? "defective"
                          : "conforming"
                        : ""
                    }
                    onBlur={(event) => {
                      if (event.target.value)
                        update(id, {
                          defective: event.target.value === "defective",
                        });
                    }}
                    onChange={(event) => {
                      if (event.target.value)
                        update(id, {
                          defective: event.target.value === "defective",
                        });
                    }}
                  >
                    <option value="" disabled>
                      {t("annotationUnchecked")}
                    </option>
                    <option value="conforming">
                      {t("annotationConforming")}
                    </option>
                    <option value="defective">
                      {t("annotationDefective")}
                    </option>
                  </select>
                </td>
                <td>
                  <input
                    aria-label={`${t("annotationDefectReason")} ${id}`}
                    disabled={!!plan}
                    value={checks[id]?.reason ?? ""}
                    maxLength={2000}
                    onChange={(event) => {
                      update(id, { reason: event.target.value });
                    }}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        className="button primary"
        disabled={!complete || busy || !!plan}
        onClick={() => {
          void prepare();
        }}
      >
        {t(busy ? "annotationBusy" : "annotationPrepare")}
      </button>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={(target) => {
            window.location.hash = objectHref({
              kind: "dataset",
              id: target.datasetId ?? sample.dataset_id,
              tab: "history",
              eventId: target.eventId,
            });
          }}
          onResolved={() => {
            setPlan(null);
            onChanged();
          }}
          onInvalidated={() => {
            setPlan(null);
          }}
        />
      )}
    </section>
  );
}
