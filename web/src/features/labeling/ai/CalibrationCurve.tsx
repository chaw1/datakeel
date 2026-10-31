import { useI18n } from "../../../i18n/useI18n";

import { percent } from "./format";

import type { components } from "../../../api/generated";

type Segment = components["schemas"]["CalibrationSegment"];

/** The measured confidence → hit-rate curve the tier thresholds were read from. */
export function CalibrationCurve({ segments }: { segments?: Segment[] }) {
  const { t } = useI18n();
  if (!segments?.length) return null;
  return (
    <>
      <h3>{t("wbCalibrationCurve")}</h3>
      <p className="muted">{t("wbCalibrationRule")}</p>
      <div className="table-wrap">
        <table aria-label={t("wbCalibrationCurve")}>
          <thead>
            <tr>
              <th>{t("wbCalibrationRange")}</th>
              <th>{t("wbTierObjects")}</th>
              <th>{t("wbTierHits")}</th>
              <th>{t("wbTierRate")}</th>
            </tr>
          </thead>
          <tbody>
            {segments.map((segment) => (
              <tr key={`${String(segment.low)}:${String(segment.high)}`}>
                <td>{`${segment.low.toFixed(2)}–${segment.high.toFixed(2)}`}</td>
                <td>{segment.objects}</td>
                <td>{segment.hits}</td>
                <td>{percent(segment.rate, t("wbUnavailable"))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
