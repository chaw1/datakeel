import { useState } from "react";

import { StandardsAnalysis } from "../features/standards/StandardsAnalysis";
import { StandardsBrowser } from "../features/standards/StandardsBrowser";
import { StandardsCoverage } from "../features/standards/StandardsCoverage";
import { StandardsHistory } from "../features/standards/StandardsHistory";
import { StandardsMappings } from "../features/standards/StandardsMappings";
import { useI18n } from "../i18n/useI18n";

import type { LineageTarget } from "../app/navigation";

import "../features/catalog/catalog.css";
import "../features/standards/standards.css";

const tabs = [
  ["fields", "stdFields"],
  ["code-lists", "stdCodes"],
  ["mappings", "stdMappings"],
  ["coverage", "stdCoverage"],
  ["history", "stdHistory"],
  ["analysis", "stdAnalysis"],
] as const;
export function StandardsPage({
  onOpenReceipt,
  onDataChanged,
}: {
  onOpenReceipt: (target: LineageTarget) => void;
  onDataChanged: () => void;
}) {
  const { t } = useI18n();
  const [tab, setTab] = useState<(typeof tabs)[number][0]>("fields");
  const [revision, setRevision] = useState(0);
  function changed() {
    setRevision((value) => value + 1);
    onDataChanged();
  }
  return (
    <div className="standards-page catalog-page">
      <div className="page-heading">
        <div>
          <h1>{t("stdNav")}</h1>
          <p>{t("stdIntro")}</p>
        </div>
      </div>
      <nav className="tabs" aria-label={t("stdNav")}>
        {tabs.map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "active" : ""}
            aria-current={tab === value ? "page" : undefined}
            onClick={() => {
              setTab(value);
            }}
          >
            {t(label)}
          </button>
        ))}
      </nav>
      <div key={`${tab}:${String(revision)}`}>
        {(tab === "fields" || tab === "code-lists") && (
          <StandardsBrowser
            collection={tab}
            onChanged={changed}
            onOpenReceipt={onOpenReceipt}
          />
        )}
        {tab === "mappings" && (
          <StandardsMappings
            onChanged={changed}
            onOpenReceipt={onOpenReceipt}
          />
        )}
        {tab === "coverage" && <StandardsCoverage />}
        {tab === "history" && (
          <StandardsHistory onChanged={changed} onOpenReceipt={onOpenReceipt} />
        )}
        {tab === "analysis" && <StandardsAnalysis />}
      </div>
    </div>
  );
}
