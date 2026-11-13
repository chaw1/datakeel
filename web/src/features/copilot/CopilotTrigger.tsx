import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";

/** Topbar trigger button for opening or collapsing the global right-side copilot drawer. */
export function CopilotTrigger({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className="button ghost small copilot-trigger"
      aria-expanded={open}
      aria-controls="copilot-drawer"
      onClick={onToggle}
    >
      <Icon name="agent" size={14} />
      <span>{t("copilotOpen")}</span>
      <kbd>{t("copilotShortcut")}</kbd>
    </button>
  );
}
