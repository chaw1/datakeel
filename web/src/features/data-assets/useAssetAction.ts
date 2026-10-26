import { useRef, useState } from "react";

import { prepareAssetAction } from "../../api/dataAssets";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { ActionPlan, ActionRun } from "../../api/types";

export function useAssetAction(onChanged: () => void) {
  const pending = useRef(false);
  const isComposing = useCompositionGuard();
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function prepare(action: string, params: unknown) {
    if (pending.current || isComposing()) return;
    pending.current = true;
    setBusy(true);
    setError("");
    setSaved(false);
    setPlan(null);
    try {
      setPlan(await prepareAssetAction(action, params));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  function resolved(run: ActionRun | null) {
    if (run?.status === "SUCCEEDED") {
      setSaved(true);
      onChanged();
    }
  }
  return { plan, busy, error, saved, prepare, resolved, isComposing };
}
