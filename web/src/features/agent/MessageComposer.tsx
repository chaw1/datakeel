import { useState } from "react";

import { Icon } from "../../components/Icon";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

export function MessageComposer({
  disabled,
  busy,
  onSend,
  initialContent = "",
}: {
  disabled: boolean;
  busy: boolean;
  onSend: (content: string) => void;
  initialContent?: string;
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
      <label className="sr-only" htmlFor="agent-message">
        {t("messageInput")}
      </label>
      <textarea
        id="agent-message"
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
    </form>
  );
}
