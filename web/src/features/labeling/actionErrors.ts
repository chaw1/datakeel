import { ApiError } from "../../api/client";

import type { Translate } from "../../i18n/context";

export type ActionProblem = "changed" | "lease" | "other";

/** Classify a failed production write so the page can explain it without raw server text. */
export function actionProblem(reason: unknown): ActionProblem {
  const text = reason instanceof Error ? reason.message.toLowerCase() : "";
  if (text.includes("lease expired") || text.includes("was reclaimed"))
    return "lease";
  if (
    reason instanceof ApiError &&
    reason.status === 409 &&
    (text.includes("changed after preparation") ||
      text.includes("changed during execution") ||
      text.includes("already has an effective assignment"))
  )
    return "changed";
  return "other";
}

/** A localized message: "changed by someone else" and lease expiry never show English internals. */
export function actionMessage(reason: unknown, t: Translate, fallback = "") {
  const problem = actionProblem(reason);
  if (problem === "changed") return t("wbChangedByOthers");
  if (problem === "lease") return t("wbLeaseLost");
  if (reason instanceof Error)
    return reason.message.replace(/^\d{3}\s+/, "") || fallback;
  return fallback;
}
