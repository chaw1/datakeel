import { useI18n } from "../../i18n/useI18n";

import type { ModelCallTrace } from "../../api/types";

export function TokenChart({ trace }: { trace: ModelCallTrace }) {
  const { t } = useI18n();
  return (
    <section className="token-chart" aria-label={t("tokenSegments")}>
      <div className="section-heading">
        <h3>{t("tokenSegments")}</h3>
        <span className="muted small">
          {t("totalInputTokens", { count: trace.usage.input_tokens })}
        </span>
      </div>
      {trace.segments.map((segment, index) => (
        <div className="token-segment" key={`${segment.name}:${String(index)}`}>
          <div>
            <span>{segment.name}</span>
            <small>
              {t(segment.stable ? "stableContext" : "volatileContext")}
            </small>
          </div>
          <div className="token-track" aria-hidden="true">
            <span
              className={segment.stable ? "stable" : "volatile"}
              style={{
                width: `${String(trace.usage.input_tokens ? (segment.tokens / trace.usage.input_tokens) * 100 : 0)}%`,
              }}
            />
          </div>
          <strong>{segment.tokens.toLocaleString()}</strong>
        </div>
      ))}
    </section>
  );
}
