import { useState } from "react";

import { replanChain } from "../../api/intents";
import { useI18n } from "../../i18n/useI18n";

import type { ActionChain, IntentResult, PageContext } from "../../api/intents";

/** Offers post-run continuation of deferred steps or live-DB replanning for failed chains. */
export function ChainReplanBar({
  chain,
  busy,
  running,
  hasContinuation,
  context,
  onReplanned,
  onError,
}: {
  chain: ActionChain;
  busy: boolean;
  running: boolean;
  hasContinuation: boolean;
  context?: PageContext;
  onReplanned: (result: IntentResult) => void;
  onError: (message: string) => void;
}) {
  const { t } = useI18n();
  const [planning, setPlanning] = useState(false);
  const deferredCount = chain.deferred_steps?.length ?? 0;
  const canPlanRemaining = chain.status === "succeeded" && deferredCount > 0;
  const canReplanFailed = chain.status === "failed";
  const chainId = chain.id ?? "";

  if (!canPlanRemaining && !canReplanFailed) {
    return deferredCount > 0 ? (
      <p className="muted small chain-deferred-note">
        {t("chainDeferredCount", { count: deferredCount })}
      </p>
    ) : null;
  }

  if (hasContinuation) {
    return (
      <p role="status" className="muted small chain-replan-ready">
        {t("chainReplannedReady")}
      </p>
    );
  }

  async function handleReplan() {
    if (planning || running || busy || !chainId) return;
    setPlanning(true);
    onError("");
    try {
      const result = await replanChain(chainId, context);
      onReplanned(result);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPlanning(false);
    }
  }

  return (
    <div className="chain-replan-bar">
      {canPlanRemaining && (
        <p className="muted small chain-deferred-note">
          {t("chainDeferredCount", { count: deferredCount })}
        </p>
      )}
      <button
        type="button"
        className={canPlanRemaining ? "button primary" : "button subtle"}
        disabled={busy || running || planning || !chainId}
        onClick={() => {
          void handleReplan();
        }}
      >
        {planning
          ? t("chainReplanning")
          : t(canPlanRemaining ? "chainPlanRemaining" : "chainReplanCurrent")}
      </button>
    </div>
  );
}
