import { useI18n } from "../../i18n/useI18n";

import type { useAnnotationSession } from "./session/useAnnotationSession";

export function SessionStatus({
  session,
  error,
}: {
  session: ReturnType<typeof useAnnotationSession>;
  error: string;
}) {
  const { t } = useI18n();
  const statusKeys = {
    saved: "wbSaved",
    pending: "wbPendingSave",
    saving: "wbSaving",
    offline: "wbOffline",
    conflict: "wbConflict",
    error: "wbSaveError",
  } as const;
  return (
    <>
      <p
        role="status"
        className={`wb-save-state wb-save-${session.status}`}
        data-save-state={session.status}
      >
        {t(statusKeys[session.status])}
      </p>
      {session.status === "conflict" && (
        <div className="wb-conflict" role="alert">
          <button
            type="button"
            onClick={() => {
              void session.reload();
            }}
          >
            {t("wbReload")}
          </button>
          <button
            type="button"
            onClick={() => {
              void session.overwrite();
            }}
          >
            {t("wbOverwrite")}
          </button>
        </div>
      )}
      {session.status === "error" && (
        <button
          type="button"
          onClick={() => {
            void session.flush();
          }}
        >
          {t("wbRetrySave")}
        </button>
      )}
      {session.storageError && <p role="alert">{t("wbStorageError")}</p>}
      {(error || session.error) && (
        <p role="alert" className="error-text">
          {error || session.error}
        </p>
      )}
    </>
  );
}
