import { useI18n } from "../../i18n/useI18n";

import { AgentObservation } from "./AgentObservation";

import type { AgentEvent } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

type Props = {
  events: AgentEvent[];
  path?: string;
  dryRun: boolean;
  busy: boolean;
  visibleReceipts: Set<AgentEvent["id"]>;
  onResolved: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
};
export function AgentSteps({ events, path = "main", ...props }: Props) {
  const { t } = useI18n();
  const rendered = new Set<string>();
  return (
    <>
      {events.map((event) => {
        const agentPath = event.agent_path;
        if (agentPath === path)
          return (
            <AgentObservation
              key={event.id}
              event={event}
              dryRun={props.dryRun}
              busy={props.busy}
              onResolved={props.onResolved}
              onOpenReceipt={props.onOpenReceipt}
              receiptVisible={props.visibleReceipts.has(event.id)}
            />
          );
        const childPath = agentPath
          .split("/")
          .slice(0, path.split("/").length + 1)
          .join("/");
        if (!agentPath.startsWith(`${path}/`) || rendered.has(childPath))
          return null;
        rendered.add(childPath);
        const children = events.filter(
          (item) =>
            item.agent_path === childPath ||
            item.agent_path.startsWith(`${childPath}/`),
        );
        const first = children.find((item) => item.agent_path === childPath);
        const tools = [
          ...new Set(
            children
              .filter((item) => item.event === "tool_call")
              .map((item) => item.call?.name)
              .filter(Boolean),
          ),
        ];
        const tokens = children
          .filter((item) => item.event === "done")
          .reduce((total, item) => total + item.tokens, 0);
        return (
          <details
            className="delegation-step"
            key={childPath}
            data-agent-path={childPath}
          >
            <summary>
              <span>
                {t("delegationStep")} ·{" "}
                <strong>
                  {first?.agent_name ?? childPath.split("/").at(-1)}
                </strong>
              </span>
              <span className="badge gray">
                {t("delegationTokens", { count: tokens })}
              </span>
            </summary>
            <p className="delegation-tools">
              <span>{t("delegationTools")}: </span>
              {tools.length ? tools.join(" · ") : t("delegationNoTools")}
            </p>
            <AgentSteps {...props} events={children} path={childPath} />
          </details>
        );
      })}
    </>
  );
}
