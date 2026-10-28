import { useI18n } from "../../i18n/useI18n";

import type { DatasheetDocument } from "../../api/datasheets";
import type { Version } from "../../api/types";

export function DatasheetControls({
  versions,
  versionId,
  language,
  mode,
  provider,
  model,
  busy,
  existing,
  onVersion,
  onLanguage,
  onMode,
  onProvider,
  onModel,
  onGenerate,
}: {
  versions: Version[];
  versionId: string;
  language: DatasheetDocument["language"];
  mode: DatasheetDocument["mode"];
  provider: "fake" | "openai" | "anthropic";
  model: string;
  busy: boolean;
  existing: boolean;
  onVersion: (value: string) => void;
  onLanguage: (value: DatasheetDocument["language"]) => void;
  onMode: (value: DatasheetDocument["mode"]) => void;
  onProvider: (value: "fake" | "openai" | "anthropic") => void;
  onModel: (value: string) => void;
  onGenerate: () => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <div className="datasheet-controls">
        <label>
          {t("datasheetVersion")}
          <select
            aria-label={t("datasheetVersion")}
            value={versionId}
            onBlur={(event) => {
              onVersion(event.target.value);
            }}
            onChange={(event) => {
              onVersion(event.target.value);
            }}
          >
            {versions.map((version, index) => (
              <option key={version.id} value={version.id}>
                {t("version")} {versions.length - index} · {version.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("datasheetLanguage")}
          <select
            aria-label={t("datasheetLanguage")}
            value={language}
            onBlur={(event) => {
              onLanguage(event.target.value === "zh" ? "zh" : "en");
            }}
            onChange={(event) => {
              onLanguage(event.target.value === "zh" ? "zh" : "en");
            }}
          >
            <option value="en">{t("datasheetEnglish")}</option>
            <option value="zh">{t("datasheetChinese")}</option>
          </select>
        </label>
        <label>
          {t("datasheetMode")}
          <select
            aria-label={t("datasheetMode")}
            value={mode}
            onBlur={(event) => {
              onMode(event.target.value === "model" ? "model" : "template");
            }}
            onChange={(event) => {
              onMode(event.target.value === "model" ? "model" : "template");
            }}
          >
            <option value="template">{t("datasheetTemplate")}</option>
            <option value="model">{t("datasheetModel")}</option>
          </select>
        </label>
        {mode === "model" && (
          <>
            <label>
              {t("provider")}
              <select
                aria-label={t("provider")}
                value={provider}
                onBlur={(event) => {
                  onProvider(
                    event.target.value === "openai"
                      ? "openai"
                      : event.target.value === "anthropic"
                        ? "anthropic"
                        : "fake",
                  );
                }}
                onChange={(event) => {
                  onProvider(
                    event.target.value === "openai"
                      ? "openai"
                      : event.target.value === "anthropic"
                        ? "anthropic"
                        : "fake",
                  );
                }}
              >
                <option value="fake">{t("datasheetFake")}</option>
                <option value="openai">{t("datasheetOpenai")}</option>
                <option value="anthropic">{t("datasheetAnthropic")}</option>
              </select>
            </label>
            <label>
              {t("datasheetModelName")}
              <input
                aria-label={t("datasheetModelName")}
                value={model}
                onChange={(event) => {
                  onModel(event.target.value);
                }}
                required
              />
            </label>
          </>
        )}
        <button
          className="button primary"
          disabled={busy || !versionId || (mode === "model" && !model.trim())}
          onClick={onGenerate}
        >
          {t(existing ? "datasheetRegenerate" : "datasheetGenerate")}
        </button>
      </div>
      {mode === "model" && <p className="muted">{t("datasheetModelHint")}</p>}
    </>
  );
}
