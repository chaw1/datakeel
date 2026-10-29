import { useRef, useState } from "react";

import { post } from "../../api/client";
import { lineageHref } from "../../app/lineageNavigation";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { PlanCard } from "../actions/PlanCard";

import { ReleaseBudget, budgetQuery, emptyBudget } from "./ReleaseBudget";

import type { operations } from "../../api/generated";
import type { ActionPlan, Version } from "../../api/types";
import type { SubmitEvent } from "react";

export function PublishRelease({
  versions,
  datasetId,
  onChanged,
}: {
  versions: Version[];
  datasetId: string;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [versionId, setVersionId] = useState(versions[0]?.id ?? "");
  const [tag, setTag] = useState("");
  const [notes, setNotes] = useState("");
  const [budget, setBudget] = useState(emptyBudget);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const revision = useRef(0);
  function invalidatePlan() {
    revision.current += 1;
    setPlan(null);
  }
  async function prepare(event: SubmitEvent) {
    event.preventDefault();
    if (busy || isComposing()) return;
    setBusy(true);
    setError("");
    const preparedRevision = revision.current;
    const body: operations["prepare_api_actions__action_type__prepare_post"]["requestBody"]["content"]["application/json"] =
      {
        dataset_id: datasetId,
        version_id: versionId,
        tag,
        notes,
      };
    try {
      const preparedPlan = await post<ActionPlan>(
        `/api/actions/publish_release/prepare${budgetQuery(budget)}`,
        body,
      );
      if (revision.current === preparedRevision) setPlan(preparedPlan);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="release-publish">
      <summary>{t("releasePublish")}</summary>
      <form className="release-form" onSubmit={(event) => void prepare(event)}>
        <label>
          {t("releaseSourceVersion")}
          <select
            aria-label={t("releaseSourceVersion")}
            value={versionId}
            onBlur={(event) => {
              setVersionId(event.target.value);
              invalidatePlan();
            }}
            onChange={(event) => {
              setVersionId(event.target.value);
              invalidatePlan();
            }}
            required
          >
            {versions.map((version) => (
              <option key={version.id} value={version.id}>
                {version.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("releaseTag")}
          <input
            value={tag}
            onChange={(event) => {
              setTag(event.target.value);
              invalidatePlan();
            }}
            placeholder={t("releaseTagExample")}
            required
          />
        </label>
        <label>
          {t("releaseNotes")}
          <textarea
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
              invalidatePlan();
            }}
            rows={3}
          />
        </label>
        <ReleaseBudget
          value={budget}
          onChange={(value) => {
            setBudget(value);
            invalidatePlan();
          }}
        />
        <button
          className="button primary"
          type="submit"
          disabled={!versions.length || busy}
        >
          {t("releaseReview")}
        </button>
      </form>
      {error && (
        <p role="alert" className="error-banner">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={(target) => {
            window.location.hash = lineageHref(target);
          }}
          onResolved={() => {
            setPlan(null);
            onChanged();
          }}
          onInvalidated={() => {
            setPlan(null);
          }}
        />
      )}
    </details>
  );
}
