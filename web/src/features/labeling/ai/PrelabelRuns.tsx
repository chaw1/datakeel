import { useEffect, useLayoutEffect, useRef } from "react";

import { useI18n } from "../../../i18n/useI18n";

import type { components } from "../../../api/generated";
import type { MessageKey } from "../../../i18n/en";

type Progress = components["schemas"]["PrelabelProgress"];

/** How often the cockpit reloads its facts while a cloud prelabel run is still going. */
export const PROGRESS_REFRESH_MS = 5000;

const statuses: Record<Progress["status"], MessageKey> = {
  running: "wbRunRunning",
  completed: "wbRunCompleted",
  failed: "wbRunFailed",
  abandoned: "wbRunAbandoned",
};

/**
 * Running cloud prelabel runs and the latest finished one: images done, spend against the
 * budget. While any run is going the cockpit is refreshed every few seconds.
 */
export function PrelabelRuns({
  runs = [],
  onRefresh,
}: {
  runs?: Progress[];
  onRefresh?: () => void;
}) {
  const { t, locale } = useI18n();
  const running = runs.some((run) => run.status === "running");
  const refresh = useRef(onRefresh);
  useLayoutEffect(() => {
    refresh.current = onRefresh;
  });
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => {
      refresh.current?.();
    }, PROGRESS_REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, [running]);
  if (!runs.length) return null;
  const count = new Intl.NumberFormat(locale);
  const money = (value: number, currency?: string | null) =>
    currency ? `${value.toFixed(4)} ${currency}` : value.toFixed(4);
  return (
    <>
      <h3>{t("wbPrelabelRuns")}</h3>
      <div className="table-wrap">
        <table aria-label={t("wbPrelabelRuns")}>
          <thead>
            <tr>
              <th>{t("wbSpendModel")}</th>
              <th>{t("wbRunStatus")}</th>
              <th>{t("wbRunImages")}</th>
              <th>{t("wbRunFailedImages")}</th>
              <th>{t("wbRunSpend")}</th>
              <th>{t("wbRunUpdated")}</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id}>
                <td>{`${run.model_name}@${run.model_version}`}</td>
                <td>
                  {t(statuses[run.status])}
                  {run.stopped && (
                    <>
                      {" "}
                      <span className="badge amber">{t("wbRunStopped")}</span>
                    </>
                  )}
                  {run.held_drafts > 0 && (
                    <>
                      {" "}
                      <span className="badge">
                        {t("wbRunHeldDrafts", {
                          count: count.format(run.held_drafts),
                        })}
                      </span>
                    </>
                  )}
                </td>
                <td>{`${count.format(run.completed_images)}/${count.format(run.planned_images)}`}</td>
                <td>{count.format(run.failed_images)}</td>
                <td>
                  {`${money(run.spent, run.currency)} / ${
                    run.budget == null
                      ? t("wbRunNoBudget")
                      : money(run.budget, run.currency)
                  }`}
                </td>
                <td>
                  {new Date(run.updated_at ?? run.started_at).toLocaleString(
                    locale,
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
