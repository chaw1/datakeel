import { useEffect, useState } from "react";

import { readLabelSet } from "../../api/intents";
import { useI18n } from "../../i18n/useI18n";
import { PlanCard } from "../actions/PlanCard";
import { prepareProduction } from "../labeling/actions";

import type { LabelSet } from "../../api/intents";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

type Label = LabelSet["labels"][number];
type Rule = NonNullable<LabelSet["guidelines"]>["rules"][number];

/** Edit a drafted, unpublished label set version, then publish it with a signature. */
export function LabelDraftEditor({
  labelSetId,
  version,
  onPublished,
  onOpenReceipt,
}: {
  labelSetId: string;
  version: number;
  onPublished: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<LabelSet | null>(null);
  const [labels, setLabels] = useState<Label[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [overview, setOverview] = useState({ zh: "", en: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<ActionPlan | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void readLabelSet(labelSetId, version)
      .then((value) => {
        if (!active) return;
        setDraft(value);
        setLabels([...value.labels]);
        setRules([...(value.guidelines?.rules ?? [])]);
        setOverview({
          zh: value.guidelines?.overview_zh ?? "",
          en: value.guidelines?.overview_en ?? "",
        });
      })
      .catch((reason: unknown) => {
        if (active) setError(String(reason));
      });
    return () => {
      active = false;
    };
  }, [labelSetId, version, revision]);
  if (!draft) return error ? <p className="error-text">{error}</p> : null;
  const source = draft.draft_source;
  function label(index: number, field: "name_zh" | "name_en", value: string) {
    setLabels(
      labels.map((item, position) =>
        position === index
          ? {
              ...item,
              [field]: value,
              name: field === "name_zh" && value ? value : item.name,
            }
          : item,
      ),
    );
  }
  function rule(index: number, field: "text_zh" | "text_en", value: string) {
    setRules(
      rules.map((item, position) =>
        position === index ? { ...item, [field]: value } : item,
      ),
    );
  }
  async function act(kind: "save" | "publish") {
    if (busy || !draft) return;
    setBusy(true);
    setError("");
    setPending(null);
    try {
      if (kind === "save") {
        const plan = await prepareProduction("create_label_set", {
          operation: "update",
          label_set_id: draft.id,
          version: draft.version,
          name: draft.name,
          labels,
          guidelines: {
            overview_zh: overview.zh,
            overview_en: overview.en,
            rules,
          },
        });
        setPending(plan);
      } else {
        setPending(
          await prepareProduction("publish_label_set", {
            label_set_id: draft.id,
            version: draft.version,
          }),
        );
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="label-draft" open={!draft.published}>
      <summary>
        {t("draftEditorTitle", { name: draft.name, version: draft.version })}
        <span className={`badge ${draft.published ? "green" : "amber"}`}>
          {t(draft.published ? "draftPublished" : "draftUnpublished")}
        </span>
      </summary>
      {source && (
        <p className="muted small">
          {t("draftSources", {
            model: source.model,
            samples: source.sample_ids.length,
            standards: source.standard_codes.join(", ") || "—",
          })}
        </p>
      )}
      <fieldset disabled={draft.published || busy}>
        <legend>{t("draftLabels")}</legend>
        {labels.map((item, index) => (
          <div className="label-draft-row" key={item.id}>
            <code>{item.id}</code>
            <input
              aria-label={t("draftNameZh", { id: item.id })}
              value={item.name_zh ?? item.name}
              onChange={(event) => {
                label(index, "name_zh", event.target.value);
              }}
            />
            <input
              aria-label={t("draftNameEn", { id: item.id })}
              value={item.name_en ?? ""}
              onChange={(event) => {
                label(index, "name_en", event.target.value);
              }}
            />
            {!!item.fields?.length && (
              <span className="muted small">
                {item.fields
                  .map((field) => field.name_zh || field.key)
                  .join(" · ")}
              </span>
            )}
          </div>
        ))}
        <label>
          {t("draftOverviewZh")}
          <textarea
            value={overview.zh}
            onChange={(event) => {
              setOverview({ ...overview, zh: event.target.value });
            }}
          />
        </label>
        <label>
          {t("draftOverviewEn")}
          <textarea
            value={overview.en}
            onChange={(event) => {
              setOverview({ ...overview, en: event.target.value });
            }}
          />
        </label>
        {rules.map((item, index) => (
          <div className="label-draft-rule" key={item.label_id}>
            <strong>{item.label_id}</strong>
            <textarea
              aria-label={t("draftRuleZh", { id: item.label_id })}
              value={item.text_zh}
              onChange={(event) => {
                rule(index, "text_zh", event.target.value);
              }}
            />
            <textarea
              aria-label={t("draftRuleEn", { id: item.label_id })}
              value={item.text_en}
              onChange={(event) => {
                rule(index, "text_en", event.target.value);
              }}
            />
            <ul className="label-draft-examples">
              {item.examples.map((example) => (
                <li key={`${example.kind}:${example.sample_id}`}>
                  <span
                    className={`badge ${example.kind === "positive" ? "green" : "red"}`}
                  >
                    {t(
                      example.kind === "positive"
                        ? "draftPositive"
                        : "draftNegative",
                    )}
                  </span>
                  <code>{example.sample_id}</code> {example.note}
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="chain-actions">
          <button
            className="button"
            type="button"
            onClick={() => {
              void act("save");
            }}
          >
            {t("draftSave")}
          </button>
          <button
            className="button primary"
            type="button"
            onClick={() => {
              void act("publish");
            }}
          >
            {t("draftPublish")}
          </button>
        </div>
      </fieldset>
      {pending && <p className="muted small">{t("draftConfirmHint")}</p>}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {pending && (
        <PlanCard
          plan={pending}
          onResolved={(run) => {
            if (run?.status !== "SUCCEEDED") return;
            setPending(null);
            setRevision((value) => value + 1);
            if (pending.action_type === "publish_label_set") onPublished();
          }}
          onInvalidated={() => {
            setPending(null);
          }}
          onOpenReceipt={onOpenReceipt}
        />
      )}
    </details>
  );
}
