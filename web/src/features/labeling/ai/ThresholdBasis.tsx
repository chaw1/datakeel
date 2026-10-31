import { useI18n } from "../../../i18n/useI18n";

import { CalibrationCurve } from "./CalibrationCurve";
import { percent, tierMessages } from "./format";

import type { components } from "../../../api/generated";
import type { MessageKey } from "../../../i18n/en";

type Thresholds = components["schemas"]["ConfidenceThresholds"];

const sources: Record<Thresholds["source"], MessageKey> = {
  configured: "wbSourceConfigured",
  calibrated: "wbSourceCalibrated",
  default: "wbSourceDefault",
};

/** The tier thresholds in effect, where they come from, and the reviewed evidence behind them. */
export function ThresholdBasis({
  thresholds,
}: {
  thresholds: Thresholds | null | undefined;
}) {
  const { t } = useI18n();
  if (!thresholds)
    return (
      <>
        <h3>{t("wbThresholds")}</h3>
        <p className="muted">{t("wbThresholdsNone")}</p>
      </>
    );
  const value = (threshold: number | null | undefined) =>
    threshold == null ? t("wbThresholdOff") : threshold.toFixed(2);
  return (
    <>
      <h3>{t("wbThresholds")}</h3>
      <dl className="wb-counts wb-thresholds">
        <div>
          <dt>{t("wbThresholdHigh")}</dt>
          <dd>{value(thresholds.high)}</dd>
        </div>
        <div>
          <dt>{t("wbThresholdLow")}</dt>
          <dd>{value(thresholds.low)}</dd>
        </div>
        <div>
          <dt>{t("wbThresholdSource")}</dt>
          <dd>{t(sources[thresholds.source])}</dd>
        </div>
      </dl>
      {thresholds.notes.includes("insufficient_samples") && (
        <p className="wb-threshold-note">
          <strong>{t("wbThresholdsInsufficient")}</strong>{" "}
          <span>
            {t("wbThresholdObjects", {
              objects: thresholds.objects,
              minimum: thresholds.minimum_objects,
            })}
          </span>
        </p>
      )}
      {!thresholds.pass_through && (
        <p className="wb-threshold-note">
          <strong>{t("wbNoPassThrough")}</strong>
        </p>
      )}
      {thresholds.notes.includes("low_capped") && (
        <p className="muted">{t("wbThresholdLowCapped")}</p>
      )}
      <p>{t("wbThresholdBasis", { objects: thresholds.objects })}</p>
      {thresholds.tiers.length > 0 && (
        <div className="table-wrap">
          <table aria-label={t("wbThresholds")}>
            <thead>
              <tr>
                <th>{t("wbTier")}</th>
                <th>{t("wbTierObjects")}</th>
                <th>{t("wbTierHits")}</th>
                <th>{t("wbTierRate")}</th>
              </tr>
            </thead>
            <tbody>
              {thresholds.tiers.map((tier) => (
                <tr key={tier.tier}>
                  <td>
                    {t("wbTierRow", { tier: t(tierMessages[tier.tier]) })}
                  </td>
                  <td>{tier.objects}</td>
                  <td>{tier.hits}</td>
                  <td>{percent(tier.rate, t("wbUnavailable"))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CalibrationCurve segments={thresholds.segments} />
    </>
  );
}
