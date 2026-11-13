import { useI18n } from "../../i18n/useI18n";

import type { ContextChip } from "./pageContext";

/** Display active workspace context chips and allow pausing context attachment. */
export function CopilotContextBar({
  chips,
  enabled,
  onToggle,
}: {
  chips: ContextChip[];
  enabled: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  return (
    <div
      className="copilot-context"
      data-paused={!enabled ? "true" : undefined}
    >
      <div className="copilot-context-row">
        <span className="eyebrow">{t("copilotContextLabel")}</span>
        <button
          type="button"
          className="text-button copilot-context-toggle"
          aria-pressed={enabled}
          onClick={onToggle}
        >
          {t(enabled ? "copilotContextUse" : "copilotContextPaused")}
        </button>
      </div>
      <div className="copilot-chips">
        {chips.length ? (
          chips.map((chip) => (
            <span className="badge gray copilot-chip" key={chip.key}>
              <span>{chip.key}:</span> <strong>{chip.value}</strong>
            </span>
          ))
        ) : (
          <span className="badge gray copilot-chip">
            {t("copilotContextGlobal")}
          </span>
        )}
      </div>
    </div>
  );
}
