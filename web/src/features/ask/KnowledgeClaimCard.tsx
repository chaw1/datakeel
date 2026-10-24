import { useI18n } from "../../i18n/useI18n";
import { KGBadge } from "../kg/KGBadge";
import { objectHref } from "../object/navigation";

import type { KnowledgeClaim } from "../../api/ask";
import type { MessageKey } from "../../i18n/en";

const consistencyLabels = {
  consistent: "knowledgeConsistent",
  not_in_system: "knowledgeNotInSystem",
  not_in_catalog: "knowledgeNotInCatalog",
} as const;
const relationLabels: Partial<Record<string, MessageKey>> = {
  owns: "knowledgeOwns",
  computed_from: "knowledgeComputedFrom",
  derived_from: "knowledgeDerivedFrom",
};

export function KnowledgeClaimCard({
  claim,
  onInspect,
}: {
  claim: KnowledgeClaim;
  onInspect: (id: string) => void;
}) {
  const { t } = useI18n();
  const other = claim.other_end;
  const relationLabel = relationLabels[claim.predicate];
  return (
    <article className="knowledge-claim" data-assertion-id={claim.assertion_id}>
      <button
        type="button"
        className="knowledge-claim-title text-button"
        onClick={() => {
          onInspect(claim.assertion_id);
        }}
      >
        <strong>{claim.head.name}</strong>
        <span>{relationLabel ? t(relationLabel) : claim.predicate}</span>
        <strong>{claim.tail.name}</strong>
      </button>
      <div className="kg-detail-meta">
        <span className={`kg-badge ${claim.relation_status}`}>
          {t(
            claim.relation_status === "accepted"
              ? "knowledgeAccepted"
              : "knowledgeCandidate",
          )}
        </span>
        <KGBadge value={claim.verification} />
        {claim.consistency && (
          <span
            className={`kg-badge ${claim.consistency === "consistent" ? "verified" : "needs_review"}`}
          >
            {t(consistencyLabels[claim.consistency])}
          </span>
        )}
      </div>
      {claim.evidence.map((evidence, index) => (
        <figure key={`${evidence.source.asset_id}:${String(index)}`}>
          <blockquote>{evidence.text}</blockquote>
          <figcaption
            title={`${evidence.source.asset_id} · ${evidence.source.version ?? ""}`}
          >
            {t("knowledgeSource", { name: evidence.document })}
          </figcaption>
        </figure>
      ))}
      {claim.subject_link && (
        <p className="knowledge-link-context">
          <span>
            {t("knowledgeSubjectLink", {
              name: claim.subject_link.entity.name,
            })}
          </span>
          <span className={`kg-badge ${claim.subject_link.link_status}`}>
            {t(
              claim.subject_link.link_status === "accepted"
                ? "knowledgeLinkAccepted"
                : "knowledgeLinkCandidate",
            )}
          </span>
        </p>
      )}
      {other.status === "not_in_catalog" &&
        claim.consistency !== "not_in_catalog" && (
          <p className="kg-missing">
            {t("knowledgeNotInCatalog")}: {other.entity.name}
          </p>
        )}
      {other.status === "linked" && other.asset_ref && (
        <p className="knowledge-link-context">
          <span>
            {t("knowledgeOtherEnd")}:{" "}
            <a
              href={objectHref({
                kind:
                  other.asset_ref.asset_type === "metric" ? "metric" : "table",
                id: other.asset_ref.asset_id,
              })}
            >
              {other.asset_ref.display_name ?? other.asset_ref.asset_id}
            </a>
          </span>
          <span className={`kg-badge ${other.link_status ?? "candidate"}`}>
            {t(
              other.link_status === "accepted"
                ? "knowledgeLinkAccepted"
                : "knowledgeLinkCandidate",
            )}
          </span>
        </p>
      )}
    </article>
  );
}
