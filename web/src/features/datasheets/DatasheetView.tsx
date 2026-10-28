import { datasheetDownload } from "../../api/datasheets";
import { translator } from "../../i18n/context";
import { useI18n } from "../../i18n/useI18n";
import { date } from "../../lib/format";

import type { DatasheetDocument, DatasheetFact } from "../../api/datasheets";
import type { MessageKey } from "../../i18n/en";

const reasons: Partial<Record<string, MessageKey>> = {
  missing_citation: "datasheetMissingCitation",
  unknown_fact: "datasheetUnknownFact",
  unsupported_number: "datasheetUnsupportedNumber",
  unsupported_date: "datasheetUnsupportedDate",
  unsupported_term: "datasheetUnsupportedTerm",
  wrong_chapter: "datasheetWrongChapter",
  invalid_output: "datasheetInvalidOutput",
};
function factText(fact: DatasheetFact): string {
  return `${fact.source_type} ${fact.source_id} · ${fact.field}: ${JSON.stringify(fact.value)}`;
}

export function DatasheetView({
  sheet,
  downloads = true,
}: {
  sheet: DatasheetDocument;
  downloads?: boolean;
}) {
  const { t, locale } = useI18n();
  const documentT = translator(sheet.language);
  return (
    <article className="datasheet-document" lang={sheet.language}>
      <div className="datasheet-document-heading">
        <div>
          <p className="mono">{sheet.version_id}</p>
          <time dateTime={sheet.created_at}>
            {date(sheet.created_at, locale)}
          </time>{" "}
          <span className="badge gray">
            {t(sheet.published ? "datasheetPublished" : "datasheetDraft")}
          </span>{" "}
          {sheet.stale && (
            <span className="badge amber">{t("datasheetStale")}</span>
          )}
        </div>
        {downloads && (
          <div className="export-actions">
            <a
              className="button"
              href={datasheetDownload(sheet.id, "markdown")}
              download
            >
              {t("datasheetMarkdown")}
            </a>
            <a
              className="button"
              href={datasheetDownload(sheet.id, "html")}
              download
            >
              {t("datasheetHtml")}
            </a>
          </div>
        )}
      </div>
      {sheet.stale && (
        <p className="warning-banner">{t("datasheetStaleDescription")}</p>
      )}
      {sheet.sections.map((section, index) => (
        <section className="datasheet-chapter" key={section.key}>
          <h3>
            {index + 1}. {section.title}
          </h3>
          {section.missing && (
            <p className="muted">{documentT("datasheetMissing")}</p>
          )}
          {!section.missing && section.sentences.length === 0 && (
            <p className="muted">{documentT("datasheetNoValidSentences")}</p>
          )}
          {section.sentences.map((sentence, sentenceIndex) => {
            const facts = sheet.facts.filter((fact) =>
              sentence.fact_ids.includes(fact.id),
            );
            return (
              <details className="datasheet-sentence" key={sentenceIndex}>
                <summary title={facts.map(factText).join("\n")}>
                  {sentence.text}
                </summary>
                <div className="datasheet-evidence">
                  <h4>{t("datasheetFacts")}</h4>
                  <dl>
                    {facts.map((fact) => (
                      <div key={fact.id}>
                        <dt>
                          <code>{fact.id}</code>
                        </dt>
                        <dd>{factText(fact)}</dd>
                        <dd>
                          {t("datasheetFactRecorded")}:{" "}
                          {date(fact.recorded_at, locale)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              </details>
            );
          })}
        </section>
      ))}
      <details className="datasheet-dropped">
        <summary>
          {t("datasheetDropped", { count: sheet.dropped_sentences.length })}
        </summary>
        {sheet.dropped_sentences.length ? (
          <ul>
            {sheet.dropped_sentences.map((sentence, index) => (
              <li key={index}>
                <p>{sentence.text}</p>
                <p className="error-text">
                  {sentence.reasons
                    .map((reason) =>
                      reasons[reason] ? t(reasons[reason]) : reason,
                    )
                    .join(" · ")}
                </p>
                <code>{sentence.fact_ids.join(", ")}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p>{t("datasheetNoDropped")}</p>
        )}
      </details>
    </article>
  );
}
