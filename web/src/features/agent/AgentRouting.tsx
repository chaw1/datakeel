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
        <p className="muted small">
          {t(
            route.requires_confirmation
              ? "workflowConfirmationHint"
              : "workflowSuggestionHint",
          )}
        </p>
      </aside>
    );
  }
  if (event.event === "done" && event.model_routes?.length) {
    const tiers: Record<string, MessageKey> = {
      simple: "modelTierSimple",
      multi_step: "modelTierMultiStep",
      high_risk: "modelTierHighRisk",
    };
    const routes = event.model_routes;
    const last = routes[routes.length - 1];
    const tierLabels = [...new Set(routes.map((route) => route.tier))]
      .map((tier) => t(tiers[tier]))
      .join(" → ");
    const fallbacks = routes.filter((route) => route.fallback_reason);
    const line = (
      <>
        <strong>{tierLabels}</strong> · <code>{last.model}</code> ·{" "}
        {t(last.pinned ? "modelPinned" : "modelAutomatic")} ·{" "}
        {t("workflowModelCalls", { count: routes.length })}
      </>
    );
    if (!fallbacks.length)
      return (
        <div className="model-routing" aria-label={t("modelRoute")}>
          {line}
        </div>
      );
    return (
      <details className="model-routing" aria-label={t("modelRoute")}>
        <summary>
          {line} · {t("modelFallbackDetails", { count: fallbacks.length })}
        </summary>
        <ul className="model-fallbacks">
          {fallbacks.map((route, index) => (
            <li key={`${route.model}:${String(index)}`}>
              <code>{route.model}</code> ·{" "}
              {t("modelFallback", {
                attempt: route.attempt,
                reason: route.fallback_reason ?? "",
              })}
            </li>
          ))}
        </ul>
      </details>
    );
  }
  return null;
}
