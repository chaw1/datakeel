import { useState } from "react";

import { Icon } from "../../components/Icon";
import { Select } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { ExecutionMode } from "../../api/types";

export function MessageComposer({
  disabled,
  busy,
  onSend,
  initialContent = "",
  inputId = "agent-message",
  mode = "auto",
  onModeChange,
  onStop,
}: {
  disabled: boolean;
  busy: boolean;
  onSend: (content: string) => void;
  initialContent?: string;
  inputId?: string;
  mode?: ExecutionMode;
  onModeChange?: (mode: ExecutionMode) => void;
  onStop?: () => void;
}) {
  const { t } = useI18n();
  const [content, setContent] = useState(initialContent);
  const isComposing = useCompositionGuard();
  return (
    <form
      className="message-composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (isComposing() || !content.trim() || disabled || busy) return;
        onSend(content.trim());
        setContent("");
      }}
    >
      <label className="sr-only" htmlFor={inputId}>
        {t("messageInput")}
      </label>
      <textarea
        id={inputId}
        value={content}
        disabled={disabled || busy}
        maxLength={80000}
        rows={3}
        placeholder={t("messagePlaceholder")}
        onKeyDown={(event) => {
          if (event.key === "Enter" && isComposing(event.nativeEvent))
            event.preventDefault();
        }}
        onChange={(event) => {
          setContent(event.target.value);
        }}
      />
      <div className="message-composer-actions">
        <label className="sr-only" htmlFor={`${inputId}-mode`}>
          {t("agentExecutionMode")}
        </label>
        <Select
          size="sm"
          id={`${inputId}-mode`}
          value={mode}
          disabled={disabled || busy || !onModeChange}
          onChange={(event) => {
            const value = event.target.value;
            if (value === "auto" || value === "plan" || value === "agent")
              onModeChange?.(value);
          }}
        >
          <option value="auto">{t("agentModeAuto")}</option>
          <option value="plan">{t("agentModePlan")}</option>
          <option value="agent">{t("agentModeAgent")}</option>
        </Select>
        {busy && onStop ? (
          <button className="button subtle" type="button" onClick={onStop}>
            {t("agentStop")}
          </button>
        ) : (
          <button
            className="button primary"
            type="submit"
            onKeyDown={(event) => {
              if (event.key === "Enter" && isComposing(event.nativeEvent))
                event.preventDefault();
            }}
            disabled={disabled || busy || !content.trim()}
          >
            <Icon name="arrow" size={16} />
            {t(busy ? "agentWorking" : "sendMessage")}
          </button>
        )}
      </div>
    </form>
  );
}
