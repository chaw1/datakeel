import { useI18n } from "../../i18n/useI18n";

import { cacheRate, money } from "./format";

import type { CostSummary } from "../../api/types";

export function CostTable({
  costs,
  onConversation,
}: {
  costs: CostSummary[];
  onConversation: (id: string) => void;
}) {
  const { t, locale } = useI18n();
  if (!costs.length)
    return (
      <div className="empty-state">
        <p>{t("noCosts")}</p>
      </div>
    );
  return (
    <div className="table-scroll">
      <table className="cost-table">
        <thead>
          <tr>
            <th>{t("costGroup")}</th>
            <th>{t("modelCalls")}</th>
            <th>{t("inputTokens")}</th>
            <th>{t("outputTokens")}</th>
            <th>{t("cacheHit")}</th>
            <th>{t("recordedCost")}</th>
            <th>{t("unknownCalls")}</th>
            <th>{t("unknownCost")}</th>
          </tr>
        </thead>
        <tbody>
          {costs.map((cost) => (
            <tr key={cost.key}>
              <td>
                {cost.group_by === "conversation" ? (
                  <button
                    className="text-button mono"
                    onClick={() => {
                      onConversation(cost.key);
                    }}
                    aria-label={t("openConversationTrace", { id: cost.key })}
                  >
                    {cost.key}
                  </button>
                ) : (
                  cost.key
                )}
              </td>
              <td>{cost.calls}</td>
              <td>{cost.input_tokens.toLocaleString()}</td>
              <td>{cost.output_tokens.toLocaleString()}</td>
              <td>{cacheRate(cost.input_tokens, cost.cache_read_tokens)}</td>
              <td>{money(cost.cost_usd, locale)}</td>
              <td>{cost.unknown_calls}</td>
              <td>{money(cost.unknown_cost_usd, locale)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
