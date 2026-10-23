import { useEffect, useRef, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import {
  aggregateInfo,
  archiveName,
  edgeKindLabel,
  graphKindLabel,
  safeNodeName,
} from "./archiveModel";

import type { ArchiveGroup } from "./archiveModel";
import type { GraphNode } from "../../api/types";

export function ArchiveCard({
  group,
  position,
  selected,
  center,
  connections,
  onSelect,
  onNavigate,
}: {
  group: ArchiveGroup;
  position: { x: number; y: number };
  selected: boolean;
  center: boolean;
  connections: number;
  onSelect: () => void;
  onNavigate?: (node: GraphNode) => void;
}) {
  const { t, locale } = useI18n();
  const [preview, setPreview] = useState(false);
  const [copied, setCopied] = useState("");
  const closeTimer = useRef<number | undefined>(undefined);
  useEffect(
    () => () => {
      window.clearTimeout(closeTimer.current);
    },
    [],
  );
  const showPreview = () => {
    window.clearTimeout(closeTimer.current);
    setPreview(true);
  };
  const hidePreview = () => {
    window.clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      setPreview(false);
    }, 120);
  };
  const { node, members } = group;
  const name = archiveName(node, locale);
  const aggregate = aggregateInfo(node);
  const label = aggregate
    ? t("graphMoreOfKind", {
        count: aggregate.count,
        kind: edgeKindLabel(aggregate.kind, t),
      })
    : safeNodeName(node, locale);
  return (
    <div
      className="archive-card"
      style={{ left: position.x, top: position.y }}
      onMouseEnter={showPreview}
      onMouseLeave={hidePreview}
      onFocus={showPreview}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) hidePreview();
      }}
    >
      <button
        type="button"
        className={`graph-node archive-card-button ${selected ? "selected" : ""} ${center ? "center" : ""} ${node.quarantined ? "quarantined" : ""} ${node.deleted ? "deleted" : ""}`}
        data-asset-type={node.asset_type}
        aria-label={t("inspectAsset", { label })}
        aria-pressed={selected}
        onClick={onSelect}
      >
        <span className="archive-name">
          {aggregate ? (
            label
          ) : (
            <>
              {name.prefix && (
                <span className="archive-prefix">{name.prefix}</span>
              )}
              <span>{name.name}</span>
              {members.length > 1 && (
                <span className="archive-multiple"> ×{members.length}</span>
              )}
            </>
          )}
        </span>
        <span className="archive-fact">
          <span className={`archive-type-dot ${node.asset_type}`} />
          {graphKindLabel(node.asset_type, t)}
          <span>{t("graphConnections", { count: connections })}</span>
        </span>
      </button>
      {preview && !aggregate && (
        <div className="archive-tooltip" role="tooltip">
          <strong>{safeNodeName(node, locale)}</strong>
          <ul>
            {members.map((member) => (
              <li key={member.id}>
                <code>{member.asset_id}</code>
                <button
                  type="button"
                  onClick={() => {
                    void navigator.clipboard
                      .writeText(member.asset_id)
                      .then(() => {
                        setCopied(member.id);
                      })
                      .catch(() => {
                        setCopied("error");
                      });
                  }}
                >
                  {copied === member.id ? t("graphCopied") : t("graphCopyId")}
                </button>
              </li>
            ))}
          </ul>
          {copied === "error" && <p role="status">{t("graphCopyFailed")}</p>}
          {onNavigate && members.length === 1 && (
            <button
              type="button"
              onClick={() => {
                onNavigate(node);
              }}
            >
              {t("graphOpenObject")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
