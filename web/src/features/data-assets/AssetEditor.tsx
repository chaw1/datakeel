import { useState } from "react";

import { classifications } from "../../api/dataAssets";
import { useI18n } from "../../i18n/useI18n";

import { AssetPlanFeedback } from "./AssetPlanFeedback";
import { useAssetAction } from "./useAssetAction";

import type { DataAsset, DataAssetDefinition } from "../../api/dataAssets";
import type { LineageTarget } from "../../app/navigation";

const types = [
  ["dataset", "assetDataset"],
  ["table", "assetTable"],
  ["metric", "assetMetric"],
] as const;
const emptyDefinition: DataAssetDefinition = {
  target: { asset_type: "dataset", asset_id: "", namespace: "default" },
  name: "",
  name_en: "",
  owner: "",
  description: "",
  classification: "internal",
  tags: [],
  synonyms: [],
  scenarios: [],
  instructions: "",
  sample: "",
};
const textFields = [
  ["name", "assetName"],
  ["name_en", "assetNameEn"],
  ["owner", "assetOwner"],
] as const;
const paragraphs = [
  ["description", "assetDescription"],
  ["instructions", "assetInstructions"],
  ["sample", "assetSample"],
] as const;
function split(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function AssetEditor({
  asset,
  onChanged,
  onOpenReceipt,
}: {
  asset?: DataAsset;
  onChanged: () => void;
  onOpenReceipt: (target: LineageTarget) => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState<DataAssetDefinition>(
    asset?.definition ?? emptyDefinition,
  );
  const [tags, setTags] = useState(draft.tags.join(", "));
  const [synonyms, setSynonyms] = useState(draft.synonyms.join(", "));
  const action = useAssetAction(onChanged);
  function prepare() {
    const definition: DataAssetDefinition = {
      ...draft,
      name: draft.name.trim(),
      owner: draft.owner.trim(),
      tags: split(tags),
      synonyms: split(synonyms),
    };
    void action.prepare(
      asset ? "update_data_asset" : "create_data_asset",
      asset ? { asset_id: asset.id, definition } : { definition },
    );
  }
  return (
    <section
      className="asset-section"
      aria-label={t(asset ? "assetEdit" : "assetNew")}
    >
      <h2>{t(asset ? "assetEdit" : "assetNew")}</h2>
      <p className="muted">{t("assetControlled")}</p>
      <form
        className="asset-form"
        onKeyDownCapture={(event) => {
          if (event.key === "Enter" && action.isComposing(event.nativeEvent))
            event.preventDefault();
        }}
        onSubmit={(event) => {
          event.preventDefault();
          prepare();
        }}
      >
        <fieldset disabled={action.busy}>
          <div className="asset-form-grid">
            {textFields.map(([field, label]) => (
              <label key={field}>
                {t(label)}
                <input
                  required={field !== "name_en"}
                  value={draft[field]}
                  onChange={(event) => {
                    setDraft({ ...draft, [field]: event.target.value });
                  }}
                />
              </label>
            ))}
            <label>
              {t("assetTargetType")}
              <select
                value={draft.target.asset_type}
                onBlur={(event) => {
                  const value = types.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (value)
                    setDraft({
                      ...draft,
                      target: { ...draft.target, asset_type: value },
                    });
                }}
                onChange={(event) => {
                  const value = types.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (value)
                    setDraft({
                      ...draft,
                      target: { ...draft.target, asset_type: value },
                    });
                }}
              >
                {types.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("assetTargetId")}
              <input
                required
                value={draft.target.asset_id}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    target: { ...draft.target, asset_id: event.target.value },
                  });
                }}
              />
            </label>
            <label>
              {t("assetTargetVersion")}
              <input
                value={draft.target.version ?? ""}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    target: {
                      ...draft.target,
                      version: event.target.value || null,
                    },
                  });
                }}
              />
            </label>
            <label>
              {t("assetClassification")}
              <select
                value={draft.classification}
                onBlur={(event) => {
                  const value = classifications.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (value) setDraft({ ...draft, classification: value });
                }}
                onChange={(event) => {
                  const value = classifications.find(
                    ([value]) => value === event.target.value,
                  )?.[0];
                  if (value) setDraft({ ...draft, classification: value });
                }}
              >
                {classifications.map(([value, label]) => (
                  <option key={value} value={value}>
                    {t(label)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("assetTags")}
              <input
                value={tags}
                onChange={(event) => {
                  setTags(event.target.value);
                }}
              />
            </label>
            <label>
              {t("assetSynonyms")}
              <input
                value={synonyms}
                onChange={(event) => {
                  setSynonyms(event.target.value);
                }}
              />
            </label>
            <label>
              {t("assetScenarios")}
              <textarea
                rows={3}
                value={draft.scenarios.join("\n")}
                onChange={(event) => {
                  setDraft({
                    ...draft,
                    scenarios: event.target.value.split("\n"),
                  });
                }}
              />
            </label>
            {paragraphs.map(([field, label]) => (
              <label className="asset-full-row" key={field}>
                {t(label)}
                <textarea
                  rows={3}
                  value={draft[field]}
                  onChange={(event) => {
                    setDraft({ ...draft, [field]: event.target.value });
                  }}
                />
              </label>
            ))}
          </div>
        </fieldset>
        <button
          className="button primary"
          type="submit"
          disabled={
            action.busy ||
            !draft.name.trim() ||
            !draft.owner.trim() ||
            !draft.target.asset_id.trim()
          }
        >
          {t(action.busy ? "assetPreparing" : "assetPrepare")}
        </button>
      </form>
      <AssetPlanFeedback
        action={action}
        onChanged={onChanged}
        onOpenReceipt={onOpenReceipt}
      />
    </section>
  );
}
