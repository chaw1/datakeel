import { useI18n } from "../../i18n/useI18n";

import type { StaticCheck } from "../../api/customOperators";

import "./custom-operators.css";

export function SourceReview({
  code,
  codeHash,
  checks,
}: {
  code: string;
  codeHash: string;
  checks: StaticCheck[];
}) {
  const { t } = useI18n();
  return (
    <section
      className="custom-source-review"
      aria-label={t("customOperatorReview")}
    >
      <h4>{t("customOperatorReview")}</h4>
      <p>{t("customOperatorReviewHint")}</p>
      <dl className="approval-fields">
        <div>
          <dt>{t("customOperatorHash")}</dt>
          <dd>
            <code>{codeHash}</code>
          </dd>
        </div>
      </dl>
      <h5>{t("customOperatorFindings")}</h5>
      {checks.length ? (
        <ul className="custom-static-findings">
          {checks.map((check, index) => (
            <li
              key={`${String(check.line)}:${String(check.column)}:${String(index)}`}
            >
              {t("customOperatorFinding", {
                line: check.line,
                rule: check.code,
                message: check.message,
              })}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t("customOperatorNoFindings")}</p>
      )}
      <h5>{t("customOperatorCode")}</h5>
      <pre className="custom-source">
        <code>{code}</code>
      </pre>
    </section>
  );
}
