import { Button, Input, Select } from "../../components/ui";
import { useI18n } from "../../i18n/useI18n";

import type { TrainingConfig } from "../../api/llmData";
import type { Version } from "../../api/types";

export function TrainingControls({
  versions,
  versionId,
  format,
  maxTokens,
  ngram,
  busy,
  onVersion,
  onFormat,
  onMaxTokens,
  onNgram,
  onAnalyze,
}: {
  versions: Version[];
  versionId: string;
  format: TrainingConfig["format"];
  maxTokens: number;
  ngram: number;
  busy: boolean;
  onVersion: (id: string) => void;
  onFormat: (format: TrainingConfig["format"]) => void;
  onMaxTokens: (value: number) => void;
  onNgram: (value: number) => void;
  onAnalyze: () => void;
}) {
  const { t } = useI18n();
  return (
    <form
      className="llm-data-controls"
      onSubmit={(event) => {
        event.preventDefault();
        onAnalyze();
      }}
    >
      <label>
        {t("llmDataVersion")}
        <Select
          value={versionId}
          disabled={busy}
          onBlur={(event) => {
            onVersion(event.target.value);
          }}
          onChange={(event) => {
            onVersion(event.target.value);
          }}
        >
          {versions.map((version) => (
            <option key={version.id} value={version.id}>
              {version.id}
            </option>
          ))}
        </Select>
      </label>
      <label>
        {t("llmDataFormat")}
        <Select
          value={format}
          disabled={busy}
          onBlur={(event) => {
            onFormat(event.target.value as TrainingConfig["format"]);
          }}
          onChange={(event) => {
            onFormat(event.target.value as TrainingConfig["format"]);
          }}
        >
          <option value="auto">{t("llmDataAuto")}</option>
          <option value="messages">{t("llmDataMessages")}</option>
          <option value="instruction">{t("llmDataInstruction")}</option>
          <option value="preference">{t("llmDataPreference")}</option>
        </Select>
      </label>
      <label>
        {t("llmDataMaxTokens")}
        <Input
          type="number"
          min={1}
          max={1000000}
          required
          value={maxTokens}
          disabled={busy}
          onChange={(event) => {
            onMaxTokens(Number(event.target.value));
          }}
        />
      </label>
      <label>
        {t("llmDataNgram")}
        <Input
          type="number"
          min={2}
          max={100}
          required
          value={ngram}
          disabled={busy}
          onChange={(event) => {
            onNgram(Number(event.target.value));
          }}
        />
      </label>
      <Button type="submit" variant="primary" disabled={busy || !versionId}>
        {t(busy ? "llmDataAnalyzing" : "llmDataAnalyze")}
      </Button>
    </form>
  );
}
