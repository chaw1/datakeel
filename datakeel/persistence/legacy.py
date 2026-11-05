# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Explicit temporary contributions for domains awaiting their migration slices.

Only this composition module may combine new store schema with legacy rows/installers.
Remove each legacy reference with its owner's W2, W3-S2 or M slice.
"""

from datakeel.core.schema import Base, SchemaContribution, SchemaInstaller
from datakeel.dataset_store.schema import SCHEMA as DATASET_SCHEMA
from datakeel.persistence import legacy_rows as rows
from datakeel.worker_store.schema import SCHEMA as WORKER_SCHEMA


def _schema(
    owner: str,
    order: int,
    rows: tuple[type[Base], ...],
    installers: tuple[SchemaInstaller, ...] = (),
) -> SchemaContribution:
    return SchemaContribution(owner=owner, order=order, rows=rows, installers=installers)


SCHEMA_CONTRIBUTIONS = (
    _schema(
        "action_store",
        0,
        (
            rows.ActionAuditRow,
            rows.ActionOperationRow,
            rows.ActionPlanRow,
            rows.ActionRunRow,
            rows.ApprovalRow,
        ),
    ),
    _schema(
        "annotation_store",
        1,
        (
            rows.AnnotationBatchRow,
            rows.AnnotationInspectionRow,
            rows.AnnotationSamplingRow,
        ),
    ),
    _schema("ask_store", 2, (rows.AskAnswerRow, rows.AskConversationRow, rows.AskSessionRow)),
    _schema(
        "asset_store",
        3,
        (
            rows.AssetApplicationRow,
            rows.AssetControlRow,
            rows.AssetGrantRow,
            rows.AssetUsageRow,
            rows.DataAssetHistoryRow,
            rows.DataAssetRow,
        ),
        (SchemaInstaller(key="asset", order=3, install=rows.install_asset_constraints),),
    ),
    _schema("catalog_store", 4, (rows.CatalogEdgeRow, rows.CatalogObjectRow)),
    _schema(
        "conversation_store",
        5,
        (
            rows.ConversationAuditRow,
            rows.ConversationRequestRow,
            rows.ConversationResumeRow,
            rows.ConversationRow,
        ),
    ),
    DATASET_SCHEMA,
    _schema("datasheet_store", 7, (rows.DatasheetJobRow, rows.DatasheetRow)),
    _schema(
        "delivery_store",
        8,
        (rows.ReleaseEntryRow, rows.ReconciliationRow, rows.ReleaseRow),
        (SchemaInstaller(key="release", order=2, install=rows.install_release_constraints),),
    ),
    _schema(
        "evidence_store",
        9,
        (rows.AssertionDecisionRow, rows.AssertionRow, rows.EvidenceCacheRow),
        (SchemaInstaller(key="evidence", order=1, install=rows.install_evidence_constraints),),
    ),
    _schema(
        "harness_store",
        10,
        (
            rows.BudgetAccountRow,
            rows.BudgetReservationRow,
            rows.EvalRunRow,
            rows.ModelCallTraceRow,
            rows.ToolInvocationRow,
        ),
    ),
    _schema("intent_store", 11, (rows.ActionChainRow,), ()),
    _schema("kg_eval_store", 12, (rows.KGEvalRunRow,), ()),
    _schema("kg_store", 13, (rows.KGCacheRow, rows.KGRunRow), ()),
    _schema(
        "llm_data_store",
        14,
        (rows.TrainingCleanRow, rows.TrainingEvaluationRow, rows.TrainingRunRow),
        (SchemaInstaller(key="llm_data", order=5, install=rows.install_llm_data_constraints),),
    ),
    _schema(
        "memory_store",
        15,
        (rows.MemoryRow, rows.MemoryAuditRow, rows.MemoryUseRow, rows.MemoryWriteRow),
    ),
    _schema("metric_store", 16, (rows.MetricAuditRow,), ()),
    _schema("operator_store", 17, (rows.CustomRunRow, rows.CustomOperatorRow)),
    _schema(
        "production_store",
        18,
        rows.REGISTERED_PRODUCTION_MODELS,
        (SchemaInstaller(key="production", order=6, install=rows.install_production_schema),),
    ),
    _schema(
        "quality_store",
        19,
        (
            rows.DqHistoryRow,
            rows.DqIssueAuditRow,
            rows.DqIssueRow,
            rows.DqResultRow,
            rows.DqRuleRow,
            rows.DqRunRow,
            rows.DqWebhookRow,
        ),
    ),
    _schema("runtime_store", 20, (rows.CheckpointWriteRow, rows.CheckpointRow)),
    _schema(
        "training_store",
        21,
        (rows.TrainingSplitRow,),
        (SchemaInstaller(key="training", order=4, install=rows.install_training_constraints),),
    ),
    _schema("transcription_store", 22, (rows.TranscriptionRow,), ()),
    _schema("worker_store", 23, (*WORKER_SCHEMA.rows,), ()),
    _schema(
        "workflow_store",
        24,
        (
            rows.WorkflowAuditRow,
            rows.WorkflowResumeRow,
            rows.WorkflowRunRow,
            rows.WorkflowStepRow,
        ),
    ),
)


def schema_contributions() -> tuple[SchemaContribution, ...]:
    """Return the explicitly assembled immutable schema contributions."""
    return SCHEMA_CONTRIBUTIONS
