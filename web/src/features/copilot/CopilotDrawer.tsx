import { useEffect, useState } from "react";

import { exportConversationUrl } from "../../api/agent";
import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { AgentCallTree } from "../agent/AgentCallTree";
import { agentHref } from "../agent/agentLink";
import { ConversationTranscript } from "../agent/ConversationTranscript";
import { MessageComposer } from "../agent/MessageComposer";

import { CopilotContextBar } from "./CopilotContextBar";
import { useCopilotSession } from "./useCopilotSession";

import type { CopilotContextSummary } from "./pageContext";
import type { ExecutionMode } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

/** Global right-side proofreading copilot drawer anchored inside the workspace shell. */
export function CopilotDrawer({
  open,
  summary,
  draftPrompt,
  onClearDraft,
  onToggle,
  onClose,
  onConversation,
  onOpenReceipt,
  onDataChanged,
}: {
  open: boolean;
  summary: CopilotContextSummary;
  draftPrompt: string;
  onClearDraft: () => void;
  onToggle: () => void;
  onClose: () => void;
  onConversation?: (id: string) => void;
  onOpenReceipt: (target: LineageTarget) => void;
  onDataChanged: () => void;
}) {
  const { t } = useI18n();
  const [mode, setMode] = useState<ExecutionMode>("auto");
  const session = useCopilotSession({
    open,
    datasetId: summary.datasetId,
    onConversation,
  });

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        (event.metaKey || event.ctrlKey) &&
        !event.shiftKey &&
        !event.altKey &&
        event.key.toLowerCase() === "j"
      ) {
        event.preventDefault();
        onToggle();
        return;
      }
      if (
        open &&
        event.key === "Escape" &&
        !document.querySelector("dialog[open]")
      ) {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onToggle, onClose]);

  if (!open) return null;

  const activeContext = session.contextEnabled ? summary.context : undefined;
  const fullPageHref = session.conversationId
    ? `${agentHref(summary.context)}&conversation=${encodeURIComponent(session.conversationId)}`.replace(
        "?&",
        "?",
      )
    : agentHref(summary.context, draftPrompt || undefined);

  function handleSend(text: string, executionMode = mode) {
    onClearDraft();
    void session.sendMessage(text, summary.context, executionMode);
  }

  return (
    <aside
      id="copilot-drawer"
      className="copilot-drawer"
      aria-label={t("copilotTitle")}
    >
      <header className="copilot-header">
        <div className="copilot-title-group">
          <h2 className="copilot-title">{t("copilotTitle")}</h2>
          <p className="muted small">{t("copilotSubtitle")}</p>
        </div>
        <div className="copilot-header-actions">
          {session.conversation && (
            <a
              className="button ghost small"
              href={exportConversationUrl(session.conversation.id, "markdown")}
              download
            >
              {t("exportConversationReport")}
            </a>
          )}
          {session.conversationId && (
            <button
              type="button"
              className="button ghost small"
              disabled={session.busy}
              onClick={() => {
                session.resetSession();
              }}
            >
              {t("copilotNewChat")}
            </button>
          )}
          <a
            className="button ghost small"
            href={fullPageHref}
            onClick={onClose}
          >
            {t("copilotOpenFull")}
          </a>
          <button
            type="button"
            className="icon-button"
            aria-label={t("copilotClose")}
            onClick={onClose}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      </header>
      <CopilotContextBar
        chips={summary.chips}
        enabled={session.contextEnabled}
        onToggle={() => {
          session.setContextEnabled((current) => !current);
        }}
      />
      {session.error && (
        <div className="error-banner copilot-error" role="alert">
          <span>{session.error}</span>
        </div>
      )}
      <div className="copilot-body">
        {session.conversation && (
          <AgentCallTree
            key={session.conversation.id}
            conversationId={session.conversation.id}
            revision={session.conversation.events.length}
            budget={session.conversation.config.budget}
          />
        )}
        {session.conversation ? (
          <ConversationTranscript
            conversation={session.conversation}
            live={session.live}
            busy={session.busy}
            context={activeContext}
            onResolved={() => {
              session.reload();
              onDataChanged();
            }}
            onOpenReceipt={onOpenReceipt}
            onReply={handleSend}
            onResume={(planId) => {
              void session.resume(planId).then(onDataChanged);
            }}
            onEscalateAgent={(request) => {
              handleSend(request, "agent");
            }}
          />
        ) : (
          <div className="copilot-empty">
            <p className="copilot-empty-title">{t("copilotEmptyTitle")}</p>
            <p className="muted small">{t("copilotEmptyHint")}</p>
            <div className="copilot-starters">
              <button
                type="button"
                className="button subtle small"
                disabled={session.busy}
                onClick={() => {
                  handleSend(t("copilotPromptInspect"));
                }}
              >
                {t("copilotPromptInspect")}
              </button>
              <button
                type="button"
                className="button subtle small"
                disabled={session.busy}
                onClick={() => {
                  handleSend(t("copilotPromptApprovals"));
                }}
              >
                {t("copilotPromptApprovals")}
              </button>
            </div>
          </div>
        )}
      </div>
      <footer className="copilot-footer">
        <MessageComposer
          key={draftPrompt}
          inputId="copilot-message"
          disabled={false}
          busy={session.busy}
          initialContent={draftPrompt}
          onSend={handleSend}
          mode={mode}
          onModeChange={setMode}
          onStop={() => {
            void session.stop();
          }}
        />
      </footer>
    </aside>
  );
}
