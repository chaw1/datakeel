import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";

import { graphKindLabel, safeNodeName } from "./archiveModel";

import type { GraphNode } from "../../api/types";

export function GraphExpansion({
  title,
  nodes,
  truncated,
  onNavigate,
  onSelect,
}: {
  title: string;
  nodes: GraphNode[];
  truncated: boolean;
  onNavigate?: (node: GraphNode) => void;
  onSelect: (node: GraphNode) => void;
}) {
  const { t, locale } = useI18n();
  const [page, setPage] = useState(1);
  const [copied, setCopied] = useState("");
  const shown = nodes.slice(0, page * 25);
  return (
    <section className="archive-expansion" aria-label={title}>
      <h3>{title}</h3>
      <p>{t("graphKnownNeighbors", { count: shown.length })}</p>
      <ul>
        {shown.map((node, index) => (
          <li key={node.id}>
            <button
              type="button"
              title={node.asset_id}
              onClick={() => {
                onSelect(node);
              }}
            >
              <span>{index + 1}.</span> {safeNodeName(node, locale)}{" "}
              <span className="muted">
                {graphKindLabel(node.asset_type, t)}
              </span>
            </button>
            <button
              type="button"
              aria-label={`${t("graphCopyId")} ${String(index + 1)}`}
              onClick={() => {
                void navigator.clipboard
                  .writeText(node.asset_id)
                  .then(() => {
                    setCopied(node.id);
                  })
                  .catch(() => {
                    setCopied("error");
                  });
              }}
            >
              {copied === node.id ? t("graphCopied") : t("graphCopyId")}
            </button>
            {onNavigate && (
              <button
                type="button"
                onClick={() => {
                  onNavigate(node);
                }}
              >
                {t("graphOpenObject")}
              </button>
            )}
          </li>
        ))}
      </ul>
      {copied === "error" && <p role="status">{t("graphCopyFailed")}</p>}
      {shown.length < nodes.length && (
        <button
          type="button"
          onClick={() => {
            setPage(page + 1);
          }}
        >
          {t("graphNextLayer")}
        </button>
      )}
      {truncated && <p>{t("graphBoundedExpansion")}</p>}
    </section>
  );
}
