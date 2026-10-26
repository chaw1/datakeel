import { localizedObjectName } from "../../i18n/graphCatalogNames";

import type { AskMetric } from "../../api/ask";
import type { Locale } from "../../i18n/context";

export function metricName(metric: AskMetric, locale: Locale): string {
  return localizedObjectName(
    "metric",
    metric.definition.name,
    locale,
    metric.definition.english_name,
  );
}

export function metricOwner(metric: AskMetric, locale: Locale): string {
  return localizedObjectName(
    "owner",
    metric.definition.owner,
    locale,
    metric.owner_english_name,
  );
}
