import { useEffect, useRef, useState } from "react";

import { Anchor } from "../../components/Anchor";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";

import { KGBadge } from "./KGBadge";
import { issueLabels } from "./labels";

import type { KGExplanation } from "../../api/kg";

export function KGRelationDrawer({
  assertionId,
  onClose,
}: {
  assertionId: string;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const dialog = useRef<HTMLDialogElement>(null);
  const [active, setActive] = useState("");
  const resource = useResource<KGExplanation>(
    `/api/kg/relations/${encodeURIComponent(assertionId)}`,
  );
  useEffect(() => {
    const previous = document.activeElement;
    if (dialog.current?.showModal) dialog.current.showModal();
    else dialog.current?.setAttribute("open", "");
    return () => {
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  const relation = resource.value?.relation;
  const detail = relation?.assertion.verification_detail;
  return (
    <dialog
      className="kg-drawer"
      ref={dialog}
      aria-label={t("kgDetails")}
      onKeyDown={(event) => {
        if (
          isComposing(event.nativeEvent) &&
          (event.key === "Escape" || event.key === "Enter")
        )
          event.preventDefault();
      }}
      onCancel={(event) => {
        event.preventDefault();
        if (!isComposing()) onClose();
      }}
    >
      <header>
        <div>
          <span className="eyebrow">{t("kgDetails")}</span>
          {relation && (
            <h2>
              {relation.head.name} → {relation.tail.name}
            </h2>
          )}
        </div>
        <button className="button" aria-label={t("kgClose")} onClick={onClose}>
          ×
        </button>
      </header>
      <ResourceState {...resource} onRetry={resource.reload} />
      {relation && (
        <>
          <div className="kg-detail-meta">
            <code>{relation.assertion.predicate}</code>
            <KGBadge value={relation.assertion.status} />
            <KGBadge value={relation.assertion.verification} />
          </div>
          <p>
            {t("kgExtractor")}: {relation.extractor} · {relation.model}
          </p>
          {!!detail?.issues.length && (
            <ul className="kg-review-issues">
              {detail.issues.map((issue, index) => (
                <li key={index}>
                  {t(issueLabels[issue.code])}
                  {issue.role
                    ? ` (${t(issue.role === "head" ? "kgHead" : "kgTail")})`
                    : ""}
                </li>
              ))}
            </ul>
          )}
          <p className="muted">{t("kgSourceLegend")}</p>
          {resource.value?.sources.map((source) => {
            const locations = (detail?.locations ?? []).filter(
              (location) =>
                location.source.asset_id === source.asset_ref.asset_id,
            );
            const checks = locations.length
              ? locations
              : detail && resource.value?.sources.length === 1
                ? [detail]
                : [];
            const roles = ["evidence", "head", "tail"] as const;
            const ranges = checks.flatMap((check, index) =>
              roles.flatMap((role, number) => {
                const span = check[role];
                return span
                  ? [
                      {
                        ...span,
                        id: `${source.asset_ref.asset_id}:${role}:${String(index)}`,
                        number: number + 1,
                      },
                    ]
                  : [];
              }),
            );
            return (
              <section className="kg-source" key={source.asset_ref.asset_id}>
                <h3>{source.filename}</h3>
                <p className="kg-source-text">
                  <Anchor
                    text={source.text}
                    ranges={ranges}
                    activeId={active}
                    onActive={setActive}
                  />
                </p>
                <div className="kg-locations">
                  {roles.map((role, number) => (
                    <div key={role}>
                      <strong>
                        {number + 1}{" "}
                        {t(
                          role === "evidence"
                            ? "kgEvidence"
                            : role === "head"
                              ? "kgHead"
                              : "kgTail",
                        )}
                      </strong>
                      {checks.some((check) => check[role]) ? (
                        checks.flatMap((check, index) =>
                          check[role]
                            ? [
                                <button
                                  className="text-button"
                                  key={index}
                                  onClick={() => {
                                    setActive(
                                      `${source.asset_ref.asset_id}:${role}:${String(index)}`,
                                    );
                                  }}
                                >
                                  {t("kgOffsets", check[role])}
                                </button>,
                              ]
                            : [],
                        )
                      ) : (
                        <span className="kg-missing">{t("kgUnlocated")}</span>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            );
          })}
        </>
      )}
    </dialog>
  );
}
