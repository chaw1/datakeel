import { useId } from "react";

import { useI18n } from "../../../i18n/useI18n";

import { percent } from "./format";

import type { components } from "../../../api/generated";

type Accuracy = components["schemas"]["PrelabelAccuracy"];
type IoUAccuracy = components["schemas"]["IoUAccuracy"];

/**
 * Object-level F1 at IoU 0.5 as the headline; hovering or opening "How it is measured"
 * gives the matching rule, both thresholds, all-hit tasks and attribute agreement.
 */
export function AccuracyHeadline({ accuracy }: { accuracy: Accuracy }) {
  const { t } = useI18n();
  const ruleId = useId();
  const none = t("wbUnavailable");
  const loose = accuracy.iou_50;
  const attributes = accuracy.attribute_agreement;
  const at = (item: IoUAccuracy) =>
    t("wbAccuracyAt", {
      threshold: String(item.threshold),
      precision: percent(item.precision, none),
      recall: percent(item.recall, none),
      f1: percent(item.f1, none),
    });
  const lines = [
    t("wbAccuracyRule"),
    at(loose),
    at(accuracy.iou_75),
    t("wbAccuracyAllHit", {
      rate: percent(loose.all_hit_rate, none),
      tasks: loose.all_hit_tasks,
      assessed: accuracy.assessed_tasks,
    }),
    t("wbAccuracyAttributes", {
      rate: percent(attributes.rate, none),
      consistent: attributes.consistent_objects,
      matched: attributes.matched_objects,
    }),
  ];
  return (
    <>
      <h3>{t("wbPrelabelAccuracy")}</h3>
      <p
        className="wb-accuracy"
        title={lines.join("\n")}
        aria-describedby={ruleId}
      >
        <strong>{percent(loose.f1, none)}</strong>{" "}
        <span className="muted">{t("wbAccuracyF1")}</span>
      </p>
      <details className="wb-accuracy-rule">
        <summary>{t("wbAccuracyHow")}</summary>
        <ul id={ruleId}>
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </details>
      <p className="muted">
        {t("wbPrelabelExactMatch", {
          rate: percent(accuracy.exact_match_rate, none),
        })}
      </p>
      <p>
        {t("wbPrelabelReference", {
          matched: accuracy.exact_match_tasks,
          assessed: accuracy.assessed_tasks,
        })}
      </p>
    </>
  );
}
