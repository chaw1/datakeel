export const customOperatorEn = {
  customOperatorsNav: "Custom operators",
  customOperatorsIntro:
    "Review Python code, approve an immutable version, and follow each sandbox run.",
  customOperatorSubmit: "Submit for code review",
  customOperatorName: "Operator name",
  customOperatorModality: "Input modality",
  customOperatorAny: "Any modality",
  customOperatorText: "Text",
  customOperatorImage: "Image",
  customOperatorCode: "Complete Python source",
  customOperatorCodeHint:
    "Export literal PARAMETER_SCHEMA and OUTPUT_METADATA_SCHEMA declarations and a run(inputs, params, ctx) function.",
  customOperatorReviewAction: "register custom operator code",
  customOperatorReview: "Code review",
  customOperatorReviewHint:
    "Review every line and the frozen code hash. Static findings identify risks; they do not establish that code is safe or replace sandbox isolation.",
  customOperatorHash: "Code SHA-256",
  customOperatorFindings: "Static checks",
  customOperatorNoFindings:
    "No prohibited patterns were detected. This is not a safety guarantee.",
  customOperatorFinding: "Line {line} · {rule}: {message}",
  customOperatorVersions: "Approved versions",
  customOperatorNoVersions: "No code has been approved yet.",
  customOperatorSubmissions: "Submissions",
  customOperatorNoSubmissions: "No code has been submitted yet.",
  customOperatorReviewPending:
    "The code is frozen in a review plan. Approval and execution of that plan register the version.",
  customOperatorOpenApproval: "Open approval sheet",
  customOperatorImmutable:
    "Changing the code creates a new hash and requires a new approval.",
  customOperatorContainerRequired:
    "Submitted code requires the container backend. Switch the service to container execution before running this version.",
  customOperatorBackend: "Execution backend",
  customOperatorImageDigest: "Container image",
  customOperatorUnsafeTitle: "Unsafe development backend enabled",
  customOperatorUnsafe:
    "Subprocess execution does not isolate host files, network, or environment secrets. Run only your own trusted code. Never use it for externally submitted code.",
  customOperatorRun: "Run in pipeline",
  customOperatorParams: "Parameters (JSON object)",
  customOperatorInvalidParams: "Parameters must be a valid JSON object.",
  customOperatorRunHint:
    "Only approved versions can run. The selected dataset is frozen into the pipeline input manifest.",
  customOperatorRuns: "Sandbox run history",
  customOperatorNoRuns: "No sandbox runs have been recorded yet.",
  customOperatorExitReason: "Exit reason",
  customOperatorResources: "Resource usage",
  customOperatorParamDigest: "Parameter digest",
  customOperatorFullRecord: "Full run record",
  customOperatorLineage: "Open dataset lineage",
  customOperatorSource: "View approved source",
  customOperatorRunQueued:
    "Pipeline queued. Refresh to follow the sandbox run and its lineage.",
};
