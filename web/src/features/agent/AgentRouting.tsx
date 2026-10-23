import { useI18n } from "../../i18n/useI18n";
import { workflowName } from "../workflows/labels";

import type { AgentEvent } from "../../api/types";
import type { MessageKey } from "../../i18n/en";

import "../workflows/workflows.css";

export function AgentRouting({ event }: { event: AgentEvent }) {
  const { t } = useI18n();
  if (event.event === "route" && event.route?.workflow_id) {
    const route = event.route;
    const workflowId = event.route.workflow_id;
    const params = new URLSearchParams({ workflow: workflowId });
    if (route.inputs?.dataset_id)
      params.set("dataset", route.inputs.dataset_id);
    return (
      <aside
        className="workflow-suggestion"
        aria-label={t("workflowSuggested")}
      >
        <span className="eyebrow">{t("workflowSuggested")}</span>
        <h3>{workflowName(workflowId, t)}</h3>
        <p className="muted small">
          {t("workflowRouteScore", { score: route.score })} ·{" "}
          {t(
            route.branch === "classifier"
              ? "workflowRouteClassifier"
              : "workflowRouteKeyword",
          )}
        </p>
        <details>
          <summary>{t("workflowRouteReason")}</summary>
          <p>{route.reason}</p>
        </details>
        <a className="button" href={`#/workflows?${params.toString()}`}>
          {t("workflowRunSuggested")}
        </a>
        <p className="muted small">{t("workflowSuggestionHint")}</p>
      </aside>
    );
  }
  if (event.event === "done" && event.model_routes?.length) {
    const tiers: Record<string, MessageKey> = {
      simple: "modelTierSimple",
      multi_step: "modelTierMultiStep",
      high_risk: "modelTierHighRisk",
    };
    return (
      <div aria-label={t("modelRoute")}>
        {event.model_routes.map((route, index) => (
          <div
            className="model-routing"
            key={`${route.model}:${String(index)}`}
          >
            <strong>{t(tiers[route.tier])}</strong> · <code>{route.model}</code>{" "}
            · {t(route.pinned ? "modelPinned" : "modelAutomatic")}
            {route.fallback_reason && (
              <p>
                {t("modelFallback", {
                  attempt: route.attempt,
                  reason: route.fallback_reason,
                })}
              </p>
            )}
          </div>
        ))}
      </div>
    );
  }
  return null;
}
