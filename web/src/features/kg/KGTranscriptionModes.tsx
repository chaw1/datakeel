import { useI18n } from "../../i18n/useI18n";

import type { KGTranscriptionProfile } from "../../api/kg";
import type { FileItem } from "../../api/types";

type Mode = KGTranscriptionProfile["mode"];

export function KGTranscriptionModes({
  mode,
  overrides,
  files,
  disabled,
  ocrOnly,
  onMode,
  onOverrides,
}: {
  mode: Mode | "";
  overrides: Record<string, Mode>;
  files: FileItem[];
  disabled: boolean;
  ocrOnly: boolean;
  onMode: (value: Mode | "") => void;
  onOverrides: (value: Record<string, Mode>) => void;
}) {
  const { t } = useI18n();
  const options = ocrOnly
    ? (["ocr"] as const)
    : (["ocr", "vlm", "auto"] as const);
  function updateMode(selected: string) {
    onMode(options.find((item) => item === selected) ?? "");
  }
  function updateOverride(fileId: string, selected: string) {
    const next = Object.fromEntries<Mode>(
      Object.entries(overrides).filter(([key]) => key !== fileId),
    );
    const value = options.find((item) => item === selected);
    if (value) next[fileId] = value;
    onOverrides(next);
  }
  return (
    <fieldset disabled={disabled} className="kg-transcription-modes">
      <legend>{t("kgTranscriptionMode")}</legend>
      <label>
        {t("kgTranscriptionMode")}
        <select
          aria-label={t("kgTranscriptionMode")}
          value={mode}
          onChange={(event) => {
            updateMode(event.target.value);
          }}
          onBlur={(event) => {
            updateMode(event.target.value);
          }}
        >
          <option value="">{t("kgProfileDefaultMode")}</option>
          {options.map((value) => (
            <option value={value} key={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <p>{t("kgAutoHint")}</p>
      {!!files.length && (
        <details>
          <summary>{t("kgFileModeOverrides")}</summary>
          {files.map((file) => (
            <label key={file.id}>
              {file.filename}
              <select
                aria-label={`${t("kgTranscriptionMode")}: ${file.filename}`}
                value={overrides[file.id] ?? ""}
                onChange={(event) => {
                  updateOverride(file.id, event.target.value);
                }}
                onBlur={(event) => {
                  updateOverride(file.id, event.target.value);
                }}
              >
                <option value="">{t("kgInheritMode")}</option>
                {options.map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </details>
      )}
    </fieldset>
  );
}
