import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { KGRelationDrawer } from "../kg/KGRelationDrawer";
import { objectHref } from "../object/navigation";

import { KnowledgeClaimCard } from "./KnowledgeClaimCard";

import "../kg/kg.css";
import "./knowledge.css";

import type { KnowledgeAnswer } from "../../api/ask";

const noSystemLabels = {
  owner: "knowledgeNoOwner",
  upstream: "knowledgeNoUpstream",
  downstream: "knowledgeNoDownstream",
  owned: "knowledgeNoSystem",
  related: "knowledgeNoSystem",
} as const;

export function KnowledgeAnswerView({
  knowledge,
}: {
  knowledge: KnowledgeAnswer;
}) {
  const { t } = useI18n();
  const [assertionId, setAssertionId] = useState("");
  const related = knowledge.intent === "related";
  const noSystem =
    knowledge.intent === "owned" && knowledge.subject?.kind === "kg_entity"
      ? "knowledgeRolesOnly"
      : noSystemLabels[knowledge.intent];
  return (
    <section
      className="knowledge-answer"
      aria-label={t(related ? "knowledgeRelated" : "knowledgeAnswered")}
    >
      <h2>{related ? t("knowledgeRelated") : knowledge.subject?.name}</h2>
      <div
        className={`knowledge-columns${related ? " knowledge-related" : ""}`}
      >
        {!related && (
          <section aria-label={t("knowledgeSystem")}>
            <h3>{t("knowledgeSystem")}</h3>
            {knowledge.system_records.length ? (
              <ul className="knowledge-system-records">
                {knowledge.system_records.map((record) => (
                  <li key={`${record.asset_ref.asset_id}:${record.relation}`}>
                    {["metric", "table", "view"].includes(
                      record.asset_ref.asset_type,
                    ) ? (
                      <a
                        href={objectHref({
                          kind:
                            record.asset_ref.asset_type === "metric"
                              ? "metric"
                              : "table",
                          id: record.asset_ref.asset_id,
                        })}
                      >
                        {record.name}
                      </a>
                    ) : (
                      <strong>{record.name}</strong>
                    )}
                    {record.name !== record.asset_ref.asset_id && (
                      <small>{record.asset_ref.asset_id}</small>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="ask-muted">{t(noSystem)}</p>
            )}
          </section>
        )}
        <section aria-label={t("knowledgeDocuments")}>
          <h3>{t("knowledgeDocuments")}</h3>
          {knowledge.claims.length ? (
            knowledge.claims.map((claim) => (
              <KnowledgeClaimCard
                key={claim.assertion_id}
                claim={claim}
                onInspect={setAssertionId}
              />
            ))
          ) : (
            <p className="ask-muted">{t("knowledgeNoDocuments")}</p>
          )}
          {knowledge.pending_ambiguous_links > 0 && (
            <p className="warning-banner">
              {t("knowledgePending", {
                count: knowledge.pending_ambiguous_links,
              })}
            </p>
          )}
        </section>
      </div>
      {assertionId && (
        <KGRelationDrawer
          key={assertionId}
          assertionId={assertionId}
          onClose={() => {
            setAssertionId("");
          }}
        />
      )}
    </section>
  );
}
