import { useState } from "react";

import { prepareRule } from "../../api/qualityRules";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { newRule, numberInput } from "./ruleDraft";
import { parameterExamples, ruleKinds } from "./ruleLabels";

import type { DqParameters, DqRule } from "../../api/qualityRules";
import type { ActionPlan } from "../../api/types";

export function RuleEditor({
  rule,
  onPrepared,
  onCancel,
}: {
  rule?: DqRule;
  onPrepared: (plan: ActionPlan) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const composing = useCompositionGuard();
  const [draft, setDraft] = useState(rule ?? newRule);
  const [parameters, setParameters] = useState(
    JSON.stringify(rule?.params ?? {}, null, 2),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function changeKind(value: string) {
    const kind = Object.keys(ruleKinds).find((key) => key === value) as
      DqRule["kind"] | undefined;
    if (kind && kind !== draft.kind) {
      setDraft({ ...draft, kind });
      setParameters(parameterExamples[kind]);
    }
  }
  function target(key: keyof DqRule["target"], value: string) {
    setDraft({
      ...draft,
      target: {
        ...draft.target,
        [key]: value || (key === "source_id" || key === "table" ? "" : null),
      },
    });
  }
  async function prepare() {
    if (busy || composing()) return;
    setError("");
    setBusy(true);
    try {
      const params: unknown = JSON.parse(parameters);
      if (!params || typeof params !== "object" || Array.isArray(params))
        throw new Error(t("dqInvalidJson"));
      onPrepared(
        await prepareRule(
          { ...draft, params: params as DqParameters },
          Boolean(rule),
        ),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("dqActionFailed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="card dq-editor"
      aria-label={t(rule ? "dqEdit" : "dqNew")}
    >
      <h2>{t(rule ? "dqEdit" : "dqNew")}</h2>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void prepare();
        }}
        onKeyDownCapture={(event) => {
          if (event.key === "Enter" && composing(event.nativeEvent))
            event.preventDefault();
        }}
      >
        <div className="dq-form-grid">
          <label>
            {t("dqId")}
            <input
              required
              disabled={Boolean(rule)}
              value={draft.id}
              maxLength={200}
              onChange={(event) => {
                setDraft({ ...draft, id: event.target.value });
              }}
            />
          </label>
          <label>
            {t("dqName")}
            <input
              required
              value={draft.name}
              maxLength={200}
              onChange={(event) => {
                setDraft({ ...draft, name: event.target.value });
              }}
            />
          </label>
          <label>
            {t("dqSource")}
            <input
              required
              value={draft.target.source_id}
              onChange={(event) => {
                target("source_id", event.target.value);
              }}
            />
          </label>
          <label>
            {t("dqSchema")}
            <input
              value={draft.target.schema_name ?? ""}
              onChange={(event) => {
                target("schema_name", event.target.value);
              }}
            />
          </label>
          <label>
            {t("dqTable")}
            <input
              required
              value={draft.target.table}
              onChange={(event) => {
                target("table", event.target.value);
              }}
            />
          </label>
          <label>
            {t("dqColumn")}
            <input
              value={draft.target.column ?? ""}
              required={
                !["volume_change", "sql_assertion"].includes(draft.kind)
              }
              onChange={(event) => {
                target("column", event.target.value);
              }}
            />
          </label>
          <label>
            {t("dqKind")}
            <select
              value={draft.kind}
              onBlur={(event) => {
                changeKind(event.target.value);
              }}
              onChange={(event) => {
                changeKind(event.target.value);
              }}
            >
              {Object.entries(ruleKinds).map(([kind, label]) => (
                <option key={kind} value={kind}>
                  {t(label)}
                </option>
              ))}
            </select>
          </label>
          <label>
            {t("dqSeverity")}
            <select
              value={draft.severity}
              onBlur={(event) => {
                setDraft({
                  ...draft,
                  severity: event.target.value === "warn" ? "warn" : "error",
                });
              }}
              onChange={(event) => {
                setDraft({
                  ...draft,
                  severity: event.target.value === "warn" ? "warn" : "error",
                });
              }}
            >
              <option value="error">{t("dqError")}</option>
              <option value="warn">{t("dqWarn")}</option>
            </select>
          </label>
          <label>
            {t("dqThreshold")}
            <input
              type="number"
              required
              min="0"
              step="any"
              value={numberInput(draft.threshold)}
              onChange={(event) => {
                setDraft({ ...draft, threshold: event.target.valueAsNumber });
              }}
            />
          </label>
          <label>
            {t("dqOwner")}
            <input
              required
              value={draft.owner}
              maxLength={200}
              onChange={(event) => {
                setDraft({ ...draft, owner: event.target.value });
              }}
            />
          </label>
          <label className="dq-full-row">
            {t("dqDataset")}
            <input
              value={draft.dataset_id ?? ""}
              onChange={(event) => {
                setDraft({ ...draft, dataset_id: event.target.value || null });
              }}
            />
          </label>
          <label className="dq-full-row">
            {t("dqSchedule")}
            <input
              value={draft.cron ?? ""}
              placeholder="0 9 * * *"
              onChange={(event) => {
                setDraft({ ...draft, cron: event.target.value || null });
              }}
            />
          </label>
          <label>
            {t("dqTimeout")}
            <input
              type="number"
              required
              min="1"
              max="60000"
              value={numberInput(draft.timeout_ms)}
              onChange={(event) => {
                setDraft({ ...draft, timeout_ms: event.target.valueAsNumber });
              }}
            />
          </label>
          <label>
            {t("dqMaxRows")}
            <input
              type="number"
              required
              min="1"
              max="100000"
              value={numberInput(draft.max_rows)}
              onChange={(event) => {
                setDraft({ ...draft, max_rows: event.target.valueAsNumber });
              }}
            />
          </label>
          <label className="dq-full-row">
            {t("dqParameters")}
            <textarea
              required
              rows={5}
              aria-describedby="dq-parameter-help"
              value={parameters}
              onChange={(event) => {
                setParameters(event.target.value);
              }}
            />
          </label>
          <p id="dq-parameter-help" className="muted dq-full-row">
            {t("dqParameterHelp")}
          </p>
          <label className="dq-check">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) => {
                setDraft({ ...draft, enabled: event.target.checked });
              }}
            />
            {t("dqEnabled")}
          </label>
        </div>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        <div className="dq-controls">
          <button type="submit" className="button primary" disabled={busy}>
            {t(busy ? "dqPreparing" : "dqReview")}
          </button>
          <button type="button" className="button subtle" onClick={onCancel}>
            {t("dqCancel")}
          </button>
        </div>
      </form>
    </section>
  );
}
