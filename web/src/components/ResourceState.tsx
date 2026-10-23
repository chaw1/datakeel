import { useI18n } from "../i18n/useI18n";
export function ResourceState({
  loading,
  error,
  onRetry,
}: {
  loading: boolean;
  error: string;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  if (error)
    return (
      <div className="error-banner" role="alert">
        <span>{error}</span>
        <button onClick={onRetry}>{t("retry")}</button>
      </div>
    );
  if (loading)
    return (
      <p className="resource-loading" role="status">
        {t("loadingData")}
      </p>
    );
  return null;
}
