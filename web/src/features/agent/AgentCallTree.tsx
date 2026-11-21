import { useEffect, useState } from "react";

import { getCallTree } from "../../api/agent";
import { ResourceState } from "../../components/ResourceState";
import { Badge } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { money } from "../traces/format";

import type { CallTree } from "../../api/types";

type OptionalTelemetry<T, Keys extends keyof T> = Omit<T, Keys> &
  Partial<Pick<T, Keys>>;
type CompatibleTree = OptionalTelemetry<
  Omit<CallTree, "nodes">,
  | "total_tokens"
  | "total_cost_usd"
  | "total_tool_calls"
  | "total_tool_elapsed_ms"
> & {
  nodes: OptionalTelemetry<
    CallTree["nodes"][number],
    "cost_usd" | "model_calls" | "tool_elapsed_ms" | "failed_tools"
  >[];
};

export function AgentCallTree({
  conversationId,
  revision = 0,
}: {
  conversationId: string;
  revision?: number;
}) {
  const { t, locale } = useI18n();
  const [open, setOpen] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const key = `${conversationId}:${String(revision)}:${String(attempt)}`;
  const [loaded, setLoaded] = useState<{
    key: string;
    value: CompatibleTree | null;
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
                  count:
                    value.total_tokens ??
                    value.nodes.reduce((total, node) => total + node.tokens, 0),
                })}
                {" · "}
                {t("agentCallTreeCost", {
                  cost: money(value.total_cost_usd ?? 0, locale),
                })}
                {" · "}
                {t("agentCallTreeTools", {
                  count: value.total_tool_calls ?? 0,
                  elapsed: Math.round(value.total_tool_elapsed_ms ?? 0),
                })}
              </p>
              {!!value.models?.length && (
                <p className="muted small">
                  {t("agentCallTreeModels", {
                    models: value.models.join(", "),
                  })}
                </p>
              )}
              {!value.nodes.length && <p>{t("agentCallTreeEmpty")}</p>}
              <ul className="agent-call-tree-nodes">
                {value.nodes.map((node) => (
                  <li key={node.id} data-child={node.parent_id !== null}>
                    <strong>{node.agent_name}</strong>{" "}
                    <Badge>
                      {t("delegationTokens", { count: node.tokens })}
                    </Badge>{" "}
                    <Badge>{money(node.cost_usd ?? 0, locale)}</Badge>{" "}
                    <Badge>
                      {t("agentModelCalls", { count: node.model_calls ?? 0 })}
                    </Badge>{" "}
                    <Badge>
                      {t("agentToolLatency", {
                        elapsed: Math.round(node.tool_elapsed_ms ?? 0),
                      })}
                    </Badge>{" "}
                    {(node.failed_tools ?? 0) > 0 && (
                      <Badge tone="warn">
                        {t("agentFailedTools", {
                          count: node.failed_tools ?? 0,
                        })}
                      </Badge>
                    )}
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
