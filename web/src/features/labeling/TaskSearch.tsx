import { useEffect, useRef, useState } from "react";

import { useI18n } from "../../i18n/useI18n";

const DEBOUNCE_MS = 300;

/** Filter the current task view by sample file name on the server. */
export function TaskSearch({
  value,
  onSearch,
}: {
  value: string;
  onSearch: (text: string) => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState(value);
  const latest = useRef(onSearch);
  useEffect(() => {
    latest.current = onSearch;
  }, [onSearch]);
  useEffect(() => {
    if (text.trim() === value.trim()) return;
    const timer = setTimeout(() => {
      latest.current(text);
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
    };
  }, [text, value]);
  return (
    <label className="wb-task-search">
      {t("wbSearchTasks")}
      <input
        type="search"
        value={text}
        maxLength={200}
        placeholder={t("wbSearchPlaceholder")}
        onChange={(event) => {
          setText(event.target.value);
        }}
      />
    </label>
  );
}
