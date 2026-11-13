import { localizedObjectName } from "../i18n/graphCatalogNames";
import { useI18n } from "../i18n/useI18n";

import type { components } from "../api/generated";

type SearchResult = components["schemas"]["SearchResult"];

/** Render command palette object handoff actions and keyboard hint footer. */
export function CommandPaletteFooter({
  selected,
  onStartConversation,
  onOpenCopilot,
}: {
  selected?: SearchResult;
  onStartConversation: (item: SearchResult) => void;
  onOpenCopilot?: (item: SearchResult) => void;
}) {
  const { t, locale } = useI18n();
  const label = selected
    ? localizedObjectName(
        selected.kind,
        selected.name,
        locale,
        selected.english_name,
      )
    : "";
  return (
    <footer>
      {selected && (
        <div className="command-footer-actions">
          <button
            type="button"
            className="text-button command-chat"
            onClick={() => {
              onStartConversation(selected);
            }}
          >
            {t("cmdConversation", { name: label })}
          </button>
          {onOpenCopilot && (
            <button
              type="button"
              className="text-button command-chat"
              onClick={() => {
                onOpenCopilot(selected);
              }}
            >
              {t("cmdCopilot", { name: label })}
            </button>
          )}
        </div>
      )}
      <p>{t("cmdHint")}</p>
    </footer>
  );
}
