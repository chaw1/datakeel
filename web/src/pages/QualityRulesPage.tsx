import { useState } from "react";

import {
  prepareDeleteRule,
  prepareRunRule,
  qualityRulesPath,
} from "../api/qualityRules";
import { lineageHref } from "../app/lineageNavigation";
import { Icon } from "../components/Icon";
import { ResourceState } from "../components/ResourceState";
import { PlanCard } from "../features/actions/PlanCard";
import { RuleDetails } from "../features/qualityRules/RuleDetails";
import { RuleEditor } from "../features/qualityRules/RuleEditor";
import { RuleIssues } from "../features/qualityRules/RuleIssues";
import { RuleList } from "../features/qualityRules/RuleList";
import { useQualityPolling } from "../features/qualityRules/useQualityPolling";
import { useI18n } from "../i18n/useI18n";
import { useResource } from "../lib/useResource";

import type { DqIssue, DqRuleView } from "../api/qualityRules";
import type { ActionPlan } from "../api/types";

import "../features/qualityRules/qualityRules.css";

export function QualityRulesPage({ params }: { params?: URLSearchParams }) {
  const { t } = useI18n();
  const filters = {
    source_id: params?.get("source_id") ?? undefined,
    table: params?.get("table") ?? undefined,
    schema_name: params?.get("schema_name") ?? undefined,
  };
  const resource = useResource<DqRuleView[]>(qualityRulesPath(filters));
  const issues = useResource<DqIssue[]>("/api/quality/issues");
  useQualityPolling(() => {
    resource.reload();
    issues.reload();
  });
  const [selectedId, setSelectedId] = useState(params?.get("rule") ?? "");
  const [search, setSearch] = useState("");
  const [editor, setEditor] = useState<"create" | "edit" | null>(null);
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const views = (resource.value ?? []).filter((view) =>
    [
      view.rule.name,
      view.rule.owner,
      view.rule.target.source_id,
      view.rule.target.table,
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(search.toLocaleLowerCase()),
  );
  const selected = resource.value?.find((view) => view.rule.id === selectedId);
  function refresh() {
    resource.reload();
    issues.reload();
    setRevision((value) => value + 1);
  }
  function prepared(value: ActionPlan) {
    setPlan(value);
    setEditor(null);
  }
  async function prepare(action: "run" | "delete") {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      prepared(
        await (action === "run"
          ? prepareRunRule(selected.rule.id)
          : prepareDeleteRule(selected.rule)),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("dqActionFailed"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>{t("dqNav")}</h1>
          <p>{t("dqDescription")}</p>
        </div>
        <div className="dq-controls">
          <button className="button" onClick={refresh}>
            <Icon name="refresh" />
            {t("refresh")}
          </button>
          <button
            className="button primary"
            onClick={() => {
              setEditor("create");
              setPlan(null);
            }}
          >
            {t("dqNew")}
          </button>
        </div>
      </div>
      <div className="dq-filter">
        <label>
          {t("dqFilter")}
          <input
            type="search"
            placeholder={t("dqFilterHint")}
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </label>
        <span>{t("dqRules", { count: views.length })}</span>
        {(filters.source_id ?? filters.table) && (
          <a href="#/quality-rules">{t("dqAllRules")}</a>
        )}
      </div>
      <ResourceState {...resource} onRetry={resource.reload} />
      {resource.value && (
        <RuleList
          views={views}
          selectedId={selectedId}
          onSelect={(id) => {
            setSelectedId(id);
            setEditor(null);
            setPlan(null);
            setError("");
          }}
        />
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
      {editor && (
        <RuleEditor
          key={editor === "edit" ? selected?.rule.id : "new"}
          rule={editor === "edit" ? selected?.rule : undefined}
          onPrepared={prepared}
          onCancel={() => {
            setEditor(null);
          }}
        />
      )}
      {plan && (
        <div className="dq-plan">
          <PlanCard
            plan={plan}
            onOpenReceipt={(target) => {
              window.location.hash = lineageHref(target);
            }}
            onInvalidated={refresh}
            onResolved={(run) => {
              if (run?.status === "SUCCEEDED" || run?.status === "QUEUED")
                refresh();
            }}
          />
          <button
            className="button subtle"
            onClick={() => {
              setPlan(null);
            }}
          >
            {t("dqCancel")}
          </button>
        </div>
      )}
      {selected && (
        <>
          <div className="dq-controls dq-selected-actions">
            <button
              className="button"
              disabled={busy}
              onClick={() => {
                void prepare("run");
              }}
            >
              {t("dqRun")}
            </button>
            <button
              className="button subtle"
              onClick={() => {
                setEditor("edit");
                setPlan(null);
              }}
            >
              {t("dqEdit")}
            </button>
            <button
              className="button subtle"
              disabled={busy}
              onClick={() => {
                void prepare("delete");
              }}
            >
              {t("dqDelete")}
            </button>
          </div>
          <RuleDetails
            key={`${selected.rule.id}:${String(revision)}`}
            view={selected}
            onPrepared={prepared}
          />
        </>
      )}
      {!selected && !editor && (
        <>
          <p className="empty-state">{t("dqChoose")}</p>
          <section className="card dq-details">
            <ResourceState
              loading={issues.loading && !issues.value}
              error={issues.error}
              onRetry={issues.reload}
            />
            {issues.value && (
              <RuleIssues issues={issues.value} onPrepared={prepared} />
            )}
          </section>
        </>
      )}
    </>
  );
}
