import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import { cacheRate, money } from "./format";
import { TokenChart } from "./TokenChart";

import type { ModelCallTrace } from "../../api/types";

export function TraceList({ traces }: { traces: ModelCallTrace[] }) {
  const { t, locale } = useI18n();
  if (!traces.length)
    return (
      <div className="card empty-state">
        <p>{t("noTraces")}</p>
      </div>
    );
  return (
    <div className="trace-list">
      {traces.map((trace) => (
        <article className="card trace-card" key={trace.id}>
          <div className="section-heading">
            <div>
              <span className="eyebrow">
                {t("traceTurn", { turn: trace.turn })}
              </span>
              <h2>{trace.model}</h2>
            </div>
            <span className="muted small">
              {date(trace.created_at, locale)}
            </span>
          </div>
          <p
            className={`badge ${trace.billing_status === "unknown" ? "amber" : "gray"}`}
          >
            {t(
              trace.billing_status === "unknown"
                ? "billingUnknown"
                : "billingActual",
            )}
          </p>
          {trace.budget_exceeded && (
            <p className="error-text">{t("budgetExceeded")}</p>
          )}
          <dl className="trace-metrics">
            <div>
              <dt>{t("inputTokens")}</dt>
              <dd>
                {trace.billing_status === "unknown"
                  ? t("unknownUsage")
                  : trace.usage.input_tokens.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt>{t("outputTokens")}</dt>
              <dd>
                {trace.billing_status === "unknown"
                  ? t("unknownUsage")
                  : trace.usage.output_tokens.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt>{t("cacheHit")}</dt>
              <dd>
                {trace.billing_status === "unknown"
                  ? t("unknownUsage")
                  : cacheRate(
                      trace.usage.input_tokens,
                      trace.usage.cache_read_tokens,
                    )}
              </dd>
            </div>
            <div>
              <dt>{t("latency")}</dt>
              <dd>
                {trace.latency_ms.toLocaleString(locale, {
                  maximumFractionDigits: 1,
                })}{" "}
                {t("milliseconds")}
              </dd>
            </div>
            <div>
              <dt>{t("recordedCost")}</dt>
              <dd>{money(trace.cost_usd, locale)}</dd>
            </div>
          </dl>
          {trace.billing_status === "unknown" ? (
            <p>
              {t("accountedTokens")}: {trace.accounted_tokens.toLocaleString()}
            </p>
          ) : (
            <TokenChart trace={trace} />
          )}
          <details>
            <summary>{t("runDetails")}</summary>
            <dl className="detail-grid">
              <div>
                <dt>{t("provider")}</dt>
                <dd>{trace.provider}</dd>
              </div>
              <div>
                <dt>{t("stopReason")}</dt>
                <dd>{trace.stop_reason}</dd>
              </div>
              <div>
                <dt>{t("cacheReadTokens")}</dt>
                <dd>{trace.usage.cache_read_tokens.toLocaleString()}</dd>
              </div>
              <div>
                <dt>{t("cacheWriteTokens")}</dt>
                <dd>{trace.usage.cache_write_tokens.toLocaleString()}</dd>
              </div>
              <div>
                <dt>{t("toolCallCount")}</dt>
                <dd>{trace.tool_calls}</dd>
              </div>
              <div>
                <dt>{t("priceVersion")}</dt>
                <dd>{trace.price_version}</dd>
              </div>
              <div>
                <dt>{t("byConversation")}</dt>
                <dd className="mono">{trace.conversation_id}</dd>
              </div>
            </dl>
          </details>
        </article>
      ))}
    </div>
  );
}
