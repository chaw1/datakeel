import { date } from "../../lib/format";
import { objectHref } from "../object/navigation";

import { MetricEvidence } from "./MetricEvidence";

import type { AskAnswer } from "../../api/ask";
import type { FootnoteItem } from "../../components/Footnotes";
import type { Translate } from "../../i18n/context";

export function answerFootnotes(
  answer: AskAnswer,
  t: Translate,
): FootnoteItem[] {
  const items: FootnoteItem[] = [];
  const query = answer.sql;
  if (answer.metric_card)
    items.push({
      id: `ask-metric-${answer.metric_card.definition.id}-${String(answer.metric_card.definition.version)}`,
      label: t("askMetric"),
      content: <MetricEvidence metric={answer.metric_card} />,
    });
  if (query) {
    items.push({
      id: `ask-sql-${answer.id ?? answer.session_id}`,
      label: t("askSql"),
      className: "ask-sql",
      content: (
        <>
          <pre>
            <code>{query.sql}</code>
          </pre>
          <h3>{t("askParameters")}</h3>
          <pre>
            <code>{JSON.stringify(query.parameters ?? {}, null, 2)}</code>
          </pre>
        </>
      ),
    });
    items.push({
      id: `ask-fields-${answer.id ?? answer.session_id}`,
      label: t("askSourceFields"),
      content: (
        <div className="ask-source-lists">
          {(["table", "column"] as const).map((kind) => (
            <section key={kind}>
              <h3>{t(kind === "table" ? "askTables" : "askColumns")}</h3>
              <ul className="ask-id-list">
                {(kind === "table" ? query.tables : query.columns).map((id) => (
                  <li key={id}>
                    <a href={objectHref({ kind, id })}>
                      <code>{id}</code>
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ),
    });
  }
  if (answer.time_range)
    items.push({
      id: `ask-time-${answer.id ?? answer.session_id}`,
      label: t("askRange"),
      content: (
        <div className="ask-time-range">
          <strong>{`[${answer.time_range.start}, ${answer.time_range.end})`}</strong>
          <small>{t("askRangeHint")}</small>
          <span>
            {t("askReferenceUsed")} ·{" "}
            {t("askUtcTime", {
              time: date(answer.reference_instant, "en", "UTC"),
            })}
          </span>
        </div>
      ),
    });
  return items;
}
