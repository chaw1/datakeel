import { useEffect, useState } from "react";

import { getCallTree } from "../../api/agent";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";

import type { CallTree } from "../../api/types";

export function AgentCallTree({
  conversationId,
  revision = 0,
}: {
  conversationId: string;
  revision?: number;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const key = `${conversationId}:${String(revision)}:${String(attempt)}`;
  const [loaded, setLoaded] = useState<{
    key: string;
    value: CallTree | null;
    error: string;
  }>({ key: "", value: null, error: "" });
  useEffect(() => {
    if (!open || !conversationId) return;
    let active = true;
    void getCallTree(conversationId)
      .then((value) => {
        if (active) setLoaded({ key, value, error: "" });
      })
      .catch((reason: unknown) => {
        if (active)
          setLoaded({
            key,
            value: null,
            error: reason instanceof Error ? reason.message : String(reason),
          });
      });
    return () => {
      active = false;
    };
  }, [open, conversationId, key]);
  const value = loaded.key === key ? loaded.value : null;
  return (
    <details
      className="agent-call-tree"
      open={open}
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary>{t("agentCallTree")}</summary>
      {open && (
        <>
          <ResourceState
            loading={loaded.key !== key}
            error={loaded.key === key ? loaded.error : ""}
            onRetry={() => {
              setAttempt((current) => current + 1);
            }}
          />
          {value && (
            <>
              <p className="muted small">
                {t("agentCallTreeTotal", {
                  count: value.nodes.reduce(
                    (total, node) => total + node.tokens,
                    0,
                  ),
                })}
              </p>
              {!value.nodes.length && <p>{t("agentCallTreeEmpty")}</p>}
              <ul className="agent-call-tree-nodes">
                {value.nodes.map((node) => (
                  <li key={node.id} data-child={node.parent_id !== null}>
                    <strong>{node.agent_name}</strong>{" "}
                    <span className="badge gray">
                      {t("delegationTokens", { count: node.tokens })}
                    </span>
                    <code>{node.agent_path}</code>
                    <p>
                      {t("delegationTools")}:{" "}
                      {node.tools.length
                        ? node.tools.join(" · ")
                        : t("delegationNoTools")}
                    </p>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </details>
  );
}
