import { useState } from "react";

import { prepareMapping } from "../../api/standards";
import { ResourceState } from "../../components/ResourceState";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";
import { useResource } from "../../lib/useResource";
import { PlanCard } from "../actions/PlanCard";
import { objectHref } from "../object/navigation";

import { percentage } from "./values";

import type {
  ColumnMapping,
  ColumnProfile,
  MappingSuggestion,
} from "../../api/standards";
import type { ActionPlan } from "../../api/types";
import type { LineageTarget } from "../../app/navigation";

export function StandardsMappings({
  onChanged,
  onOpenReceipt,
}: {
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const composing = useCompositionGuard();
  const suggestions = useResource<MappingSuggestion[]>(
    "/api/standards/suggestions",
  );
  const profiles = useResource<ColumnProfile[]>("/api/standards/profiles");
  const mappings = useResource<ColumnMapping[]>("/api/standards/mappings");
  const [search, setSearch] = useState("");
  const [plan, setPlan] = useState<ActionPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const rows =
    suggestions.value?.filter((item) =>
      `${item.column_id} ${profiles.value?.find((profile) => profile.column_id === item.column_id)?.name ?? ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
    ) ?? [];
  async function prepare(column_id: string, standard_code: string) {
    if (busy || composing()) return;
    setBusy(true);
    setError("");
    try {
      setPlan(await prepareMapping({ column_id, standard_code }));
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : t("stdPrepareFailed"),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card standards-section">
      <p>{t("stdMappingIntro")}</p>
      <label>
        {t("stdSearchColumns")}
        <input
          type="search"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
          }}
        />
      </label>
      {[suggestions, profiles, mappings].map((resource, index) => (
        <ResourceState
          key={index}
          loading={resource.loading}
          error={resource.error}
          onRetry={resource.reload}
        />
      ))}
      {error && (
        <p className="error-text" role="alert">
          {error}
        </p>
      )}
      {plan && (
        <PlanCard
          plan={plan}
          onOpenReceipt={onOpenReceipt}
          onInvalidated={onChanged}
          onResolved={(run) => {
            if (run?.status === "SUCCEEDED") onChanged();
          }}
        />
      )}
      {!suggestions.loading && (
        <ul className="standards-candidates">
          {rows.map((item) => {
            const profile = profiles.value?.find(
              (entry) => entry.column_id === item.column_id,
            );
            const confirmed = mappings.value?.find(
              (entry) => entry.column_id === item.column_id,
            );
            return (
              <li key={item.column_id}>
                <h3>
                  <a
                    href={objectHref({
                      kind: "column",
                      id: item.column_id,
                      tab: "facts",
                    })}
                  >
                    {profile?.name ?? item.column_id}
                  </a>
                </h3>
                <p className="mono">{item.column_id}</p>
                {confirmed && (
                  <p className="badge green">
                    {t("stdMapped", { code: confirmed.standard_code })}
                  </p>
                )}
                {item.candidates.map((candidate) => (
                  <div
                    className="standards-candidate"
                    key={candidate.standard_code}
                  >
                    <strong>
                      {candidate.standard_code} · {t("stdScore")}:{" "}
                      {percentage(candidate.score)}
                    </strong>
                    <ul aria-label={t("stdReasons")}>
                      {candidate.reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                    <button
                      className="button subtle"
                      disabled={
                        busy ||
                        candidate.standard_code === confirmed?.standard_code
                      }
                      onKeyDown={(event) => {
                        if (composing(event.nativeEvent))
                          event.preventDefault();
                      }}
                      onClick={() => {
                        void prepare(item.column_id, candidate.standard_code);
                      }}
                    >
                      {t("stdConfirmMapping")}
                    </button>
                  </div>
                ))}
                {!item.candidates.length && (
                  <p className="muted">{t("stdNoSuggestion")}</p>
                )}
              </li>
            );
          })}
          {!rows.length && <li>{t("stdNoColumns")}</li>}
        </ul>
      )}
    </section>
  );
}
