import { useRef, useState } from "react";

import { post } from "../../api/client";
import { assetPath, scopeLabels } from "../../api/dataAssets";
import { useI18n } from "../../i18n/useI18n";
import { useCompositionGuard } from "../../lib/useCompositionGuard";

import type { AccessScope, AssetApplication } from "../../api/dataAssets";
import type { components } from "../../api/generated";

export function AssetAccessForm({
  assetId,
  onChanged,
}: {
  assetId: string;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const pending = useRef(false);
  const requestKey = useRef<{ payload: string; id: string } | null>(null);
  const isComposing = useCompositionGuard();
  const [actor, setActor] = useState("local-user");
  const [purpose, setPurpose] = useState("");
  const [expires, setExpires] = useState("");
  const [scopes, setScopes] = useState<AccessScope[]>(["query"]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function submit() {
    if (
      pending.current ||
      isComposing() ||
      !actor.trim() ||
      !purpose.trim() ||
      !expires ||
      !scopes.length
    )
      return;
    pending.current = true;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const body: components["schemas"]["AssetApplicationCreate"] = {
        applicant: actor.trim(),
        purpose: purpose.trim(),
        scopes,
        expires_at: new Date(expires).toISOString(),
      };
      const payload = JSON.stringify(body);
      if (requestKey.current?.payload !== payload)
        requestKey.current = { payload, id: crypto.randomUUID() };
      await post<AssetApplication>(`${assetPath(assetId)}/applications`, {
        ...body,
        operation_id: requestKey.current.id,
      });
      requestKey.current = null;
      setSaved(true);
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="asset-section">
      <h2>{t("assetApply")}</h2>
      <form
        className="asset-form"
        onKeyDownCapture={(event) => {
          if (event.key === "Enter" && isComposing(event.nativeEvent))
            event.preventDefault();
        }}
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label>
          {t("assetActor")}
          <input
            required
            value={actor}
            disabled={busy}
            onChange={(event) => {
              setActor(event.target.value);
            }}
          />
        </label>
        <p className="muted">{t("assetActorHelp")}</p>
        <label>
          {t("assetPurpose")}
          <textarea
            required
            value={purpose}
            disabled={busy}
            onChange={(event) => {
              setPurpose(event.target.value);
            }}
          />
        </label>
        <label>
          {t("assetExpires")}
          <input
            type="datetime-local"
            required
            value={expires}
            disabled={busy}
            onChange={(event) => {
              setExpires(event.target.value);
            }}
          />
        </label>
        <fieldset disabled={busy}>
          <legend>{t("assetScopes")}</legend>
          <div className="asset-scope-options">
            {(Object.keys(scopeLabels) as AccessScope[]).map((scope) => (
              <label key={scope}>
                <input
                  type="checkbox"
                  checked={scopes.includes(scope)}
                  onChange={(event) => {
                    setScopes(
                      event.target.checked
                        ? [...scopes, scope]
                        : scopes.filter((value) => value !== scope),
                    );
                  }}
                />
                {t(scopeLabels[scope])}
              </label>
            ))}
          </div>
        </fieldset>
        <button
          className="button primary"
          disabled={
            busy ||
            !scopes.length ||
            !actor.trim() ||
            !purpose.trim() ||
            !expires
          }
        >
          {t(busy ? "assetSubmitting" : "assetSubmit")}
        </button>
        {error && (
          <p className="error-text" role="alert">
            {error}
          </p>
        )}
        {saved && <p role="status">{t("assetApplicationSaved")}</p>}
      </form>
    </section>
  );
}
