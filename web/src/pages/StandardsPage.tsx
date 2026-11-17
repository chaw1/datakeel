import { useState } from "react";

import { PageHeader, SegmentedTabs } from "../components/ui";
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
      <PageHeader title={t("stdNav")} subtitle={t("stdIntro")} />
      <SegmentedTabs
        label={t("stdNav")}
        activeId={tab}
        onSelect={setTab}
        items={tabs.map(([id, label]) => ({ id, label: t(label) }))}
      />
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
