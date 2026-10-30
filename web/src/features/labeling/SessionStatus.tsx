import { useI18n } from "../../i18n/useI18n";

import type { useAnnotationSession } from "./session/useAnnotationSession";

export function SessionStatus({
  session,
  error,
  locked = false,
}: {
  session: ReturnType<typeof useAnnotationSession>;
  error: string;
  /** The task was taken back: saving is over, the lock notice explains the kept draft. */
  locked?: boolean;
}) {
  const { t } = useI18n();
  const statusKeys = {
    saved: "wbSaved",
    pending: "wbPendingSave",
    saving: "wbSaving",
    offline: "wbOffline",
    conflict: "wbConflict",
    error: "wbSaveError",
    incomplete: "wbIncomplete",
  } as const;
  if (locked)
    return (
      <>
        <p
          role="status"
          className="wb-save-state wb-save-locked"
          data-save-state="locked"
        >
          {session.dirty ? t("wbDraftKeptLocally") : t("wbSaved")}
        </p>
        {session.storageError && <p role="alert">{t("wbStorageError")}</p>}
      </>
    );
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
