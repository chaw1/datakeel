/** Refusal and clarification reasons, worded from the codes the server records. */
export const askReasonEn = {
  askWhyAmbiguousMetric:
    "The question matches several metrics. Choose the definition you need.",
  askWhyUnresolvedMetric:
    "The catalog objects this metric refers to are not resolved yet, so the question cannot run.",
  askWhyTimeUnparsed: "The time condition could not be read reliably: {notes}",
  askWhyGenericMetric:
    "The question only names a general term that fits several metrics. Choose the definition you need.",
  askWhyNoMetric:
    "No registered metric answers this question. These are the closest metrics.",
  askWhySelectedMetricMissing:
    "The selected metric does not exist. Choose a registered metric.",
  askWhySelectedMetricUnresolved:
    "The selected metric or the question's conditions are not resolved yet, so the question cannot run.",
  askWhyExecutionFailed:
    "The registered metric could not run just now ({notes}).",
  askWhyTimeNotUnderstood:
    "The time condition could not be read reliably: {fragments} was not understood.",
  askWhyUnsupportedCalculation:
    "The registered metric does not support the requested calculation: {fragments}.",
  askWhyUnclearCondition: "Clarify the dimension conditions: {details}",
  askWhyNotUnderstood: "{fragment} was not understood",
  askWhyShareNeedsGrouping:
    "A share of result rows needs a grouping dimension or a time grain.",
  askWhyComparisonPeriodMismatch:
    "The comparison period does not match the complete time range asked for. Specify the month or quarter.",
  askWhyYearOverYearNeedsRange:
    "Specify the time range for the year-over-year comparison.",
  askWhyPreviousPeriodNeedsRange:
    "Specify the time range for the period-over-period comparison.",
  askWhySamePeriodNeedsRange:
    "Specify the bounded time range that “the same period” refers to.",
  askWhyFollowupTimeUnparsed:
    "The follow-up's time condition cannot be used: {notes}",
  askWhyFollowupMetricUnavailable:
    "The previous turn's metric is not available under its current registered definition.",
  askWhyFollowupDimensionsUnclear:
    "It is unclear whether the new metric keeps the previous turn's dimensions. Specify the filters and grouping.",
  askWhyFollowupComparisonUnclear:
    "Specify the comparison and time grouping you need. Negated or conflicting changes are not supported.",
  askWhyFollowupChangeUnclear:
    "It is unclear what the follow-up changes. Specify the metric, time, dimension value or grouping.",
  knowledgeWhyPending:
    "{count} links from document claims are waiting for confirmation.",
  knowledgeWhyMissingCatalog:
    "{name} is in the catalog, but neither the system nor any document records what this question needs.",
  knowledgeWhyMissingGraph:
    "{name} resolves to a graph entity, but neither the system nor any document records what this question needs.",
  knowledgeWhySubject: "The subject",
  askProfileWhyNoProfile: "No published time-series profile is available.",
  askProfileWhyUnknownSubject: "The selected dataset has no current profile.",
  askProfileWhyUnknownColumn:
    "No current profile records the requested temperature column.",
  askProfileWhyAmbiguousDataset:
    "Choose one dataset before comparing its devices.",
  askProfileWhyIncompleteProfile:
    "Current gap measurements are incomplete; devices cannot be ranked reliably.",
  askProfileWhyNoRecordedGaps:
    "No device gap intervals are recorded in the current version.",
  askProfileRankedGapCount:
    "Ranked by sampling-axis gap interval count in the published version. Only devices with recorded gaps are compared. A table containing temperature does not establish temperature-only missing values.",
  askProfileRankedDuration:
    "Ranked by sampling-axis total missing duration in the published version. Only devices with recorded gaps are compared. A table containing temperature does not establish temperature-only missing values.",
  askChartCaption: "{name}: {rows} result rows; {columns}",
};
