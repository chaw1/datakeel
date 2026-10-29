import { useState } from "react";

import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import { TrainingStratificationSource } from "./TrainingStratificationSource";

import type { SplitRequest } from "../../api/training";
import type { SubmitEvent } from "react";

export function TrainingForm({
  busy,
  onSubmit,
  onChange,
}: {
  busy: boolean;
  onSubmit: (request: SplitRequest, preview: boolean) => void;
  onChange?: () => void;
}) {
  const { t } = useI18n();
  const isComposing = useCompositionGuard();
  const [name, setName] = useState("baseline-80-10-10");
  const [ratios, setRatios] = useState({
    train: "0.8",
    val: "0.1",
    test: "0.1",
  });
  const [seed, setSeed] = useState("42");
  const [stratify, setStratify] = useState(true);
  const [stratificationSource, setStratificationSource] =
    useState<SplitRequest["stratification_source"]>("all");
  const [group, setGroup] = useState("");
  const [avoidLeakage, setAvoidLeakage] = useState(true);
  const [imageThreshold, setImageThreshold] = useState("8");
  const [textThreshold, setTextThreshold] = useState("3");
  const [source, setSource] = useState<"generated" | "directory">("generated");
  const ratioValues = Object.values(ratios).map(Number);
  const ratiosValid =
    Number(ratios.train) > 0 &&
    ratioValues.filter((value) => value > 0).length >= 2 &&
    Math.abs(ratioValues.reduce((sum, value) => sum + value, 0) - 1) < 1e-9;
  const invalid = !name.trim() || (source === "generated" && !ratiosValid);
  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || invalid || isComposing()) return;
    onSubmit(
      {
        name: name.trim(),
        ratios:
          source === "directory"
            ? { train: 0.8, val: 0.1, test: 0.1 }
            : {
                train: Number(ratios.train),
                val: Number(ratios.val),
                test: Number(ratios.test),
              },
        seed: Number(seed),
        stratify,
        stratification_source: stratificationSource,
        group_field: group.trim() || null,
        avoid_leakage: avoidLeakage,
        image_threshold: Number(imageThreshold),
        text_threshold: Number(textThreshold),
        source,
      },
      event.nativeEvent.submitter?.getAttribute("value") === "preview",
    );
  }
  return (
    <form className="training-form" onSubmit={submit} onChange={onChange}>
      <label>
        {t("trainingName")}
        <input
          value={name}
          required
          maxLength={120}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </label>
      <label>
        {t("trainingSource")}
        <select
          aria-label={t("trainingSource")}
          value={source}
          onChange={(event) => {
            setSource(
              event.target.value === "directory" ? "directory" : "generated",
            );
          }}
          onBlur={(event) => {
            setSource(
              event.target.value === "directory" ? "directory" : "generated",
            );
          }}
        >
          <option value="generated">{t("trainingGenerated")}</option>
          <option value="directory">{t("trainingDirectory")}</option>
        </select>
      </label>
      <fieldset className="training-ratios" disabled={source === "directory"}>
        <legend>{t("trainingRatios")}</legend>
        {(["train", "val", "test"] as const).map((split) => (
          <label key={split}>
            {t(
              split === "train"
                ? "trainingTrain"
                : split === "val"
                  ? "trainingVal"
                  : "trainingTest",
            )}
            <input
              type="number"
              min="0"
              max="1"
              step="any"
              required
              value={ratios[split]}
              onChange={(event) => {
                setRatios({ ...ratios, [split]: event.target.value });
              }}
            />
          </label>
        ))}
        <p className="muted small">{t("trainingRatioHint")}</p>
      </fieldset>
      <label>
        {t("trainingSeed")}
        <input
          type="number"
          min="0"
          step="1"
          required
          value={seed}
          disabled={source === "directory"}
          onChange={(event) => {
            setSeed(event.target.value);
          }}
        />
      </label>
      <label>
        {t("trainingGroup")}
        <input
          value={group}
          placeholder={t("trainingGroupHint")}
          onChange={(event) => {
            setGroup(event.target.value);
          }}
        />
      </label>
      <label className="training-check">
        <input
          type="checkbox"
          checked={stratify}
          disabled={source === "directory"}
          onChange={(event) => {
            setStratify(event.target.checked);
          }}
        />
        {t("trainingStratify")}
      </label>
      <TrainingStratificationSource
        value={stratificationSource}
        disabled={source === "directory" || !stratify}
        onChange={setStratificationSource}
      />
      <label className="training-check">
        <input
          type="checkbox"
          checked={avoidLeakage}
          disabled={source === "directory"}
          onChange={(event) => {
            setAvoidLeakage(event.target.checked);
          }}
        />
        {t("trainingAvoidLeakage")}
      </label>
      <label>
        {t("trainingImageThreshold")}
        <input
          type="number"
          min="0"
          max="64"
          step="1"
          required
          value={imageThreshold}
          onChange={(event) => {
            setImageThreshold(event.target.value);
          }}
        />
      </label>
      <label>
        {t("trainingTextThreshold")}
        <input
          type="number"
          min="0"
          max="64"
          step="1"
          required
          value={textThreshold}
          onChange={(event) => {
            setTextThreshold(event.target.value);
          }}
        />
      </label>
      {source === "generated" && !ratiosValid && (
        <p className="error-text" role="alert">
          {t("trainingInvalidRatios")}
        </p>
      )}
      <div className="training-controls">
        <button
          className="button"
          type="submit"
          value="preview"
          disabled={busy || invalid}
        >
          {t("trainingPreview")}
        </button>
        <button
          className="button primary"
          type="submit"
          value="save"
          disabled={busy || invalid}
        >
          {t("trainingSave")}
        </button>
      </div>
    </form>
  );
}
