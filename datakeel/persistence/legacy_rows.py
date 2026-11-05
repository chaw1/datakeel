# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Temporary explicit schema wiring for domains awaiting their listed migration slice."""

from datakeel.storage.action_rows import (
    ActionAuditRow,
    ActionOperationRow,
    ActionPlanRow,
    ActionRunRow,
    ApprovalRow,
)
from datakeel.storage.annotation_rows import (
    AnnotationBatchRow,
    AnnotationInspectionRow,
    AnnotationSamplingRow,
)
from datakeel.storage.ask_conversation_rows import AskConversationRow
from datakeel.storage.ask_rows import AskAnswerRow, AskSessionRow
from datakeel.storage.budget_rows import BudgetAccountRow, BudgetReservationRow
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.checkpoint_store import CheckpointRow, CheckpointWriteRow
from datakeel.storage.conversation_rows import (
    ConversationAuditRow,
    ConversationRequestRow,
    ConversationResumeRow,
    ConversationRow,
)
from datakeel.storage.custom_rows import CustomOperatorRow, CustomRunRow
from datakeel.storage.data_asset_rows import (
    AssetApplicationRow,
    AssetControlRow,
    AssetGrantRow,
    AssetUsageRow,
    DataAssetHistoryRow,
    DataAssetRow,
    install_asset_constraints,
)
from datakeel.storage.datasheet_job_rows import DatasheetJobRow
from datakeel.storage.datasheet_rows import DatasheetRow
from datakeel.storage.delivery_rows import ReconciliationRow
from datakeel.storage.dq_rows import (
    DqHistoryRow,
    DqIssueAuditRow,
    DqIssueRow,
    DqResultRow,
    DqRuleRow,
    DqRunRow,
    DqWebhookRow,
)
from datakeel.storage.evidence_constraints import install_evidence_constraints
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow, EvidenceCacheRow
from datakeel.storage.file_discovery import (
    FileDiscoveryCheckpointRow,
    FileDiscoveryRow,
    install_file_discovery,
)
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.harness_rows import EvalRunRow, ModelCallTraceRow
from datakeel.storage.intent_rows import ActionChainRow
from datakeel.storage.kg_eval_rows import KGEvalRunRow
from datakeel.storage.kg_rows import KGCacheRow, KGRunRow
from datakeel.storage.llm_data_constraints import install_llm_data_constraints
from datakeel.storage.llm_data_rows import TrainingCleanRow, TrainingEvaluationRow, TrainingRunRow
from datakeel.storage.memory_rows import MemoryAuditRow, MemoryRow, MemoryUseRow, MemoryWriteRow
from datakeel.storage.metric_audit import MetricAuditRow
from datakeel.storage.production_schema import (
    REGISTERED_PRODUCTION_MODELS,
    install_production_schema,
)
from datakeel.storage.release_constraints import install_release_constraints
from datakeel.storage.release_rows import ReleaseEntryRow, ReleaseRow
from datakeel.storage.tool_rows import ToolInvocationRow
from datakeel.storage.training_rows import TrainingSplitRow, install_training_constraints
from datakeel.storage.transcription_rows import TranscriptionRow
from datakeel.storage.upload_rows import UploadRow
from datakeel.storage.workflow_rows import (
    WorkflowAuditRow,
    WorkflowResumeRow,
    WorkflowRunRow,
    WorkflowStepRow,
)

_REGISTERED_MODELS = (
    ActionChainRow,
    TrainingSplitRow,
    TrainingCleanRow,
    TrainingEvaluationRow,
    TrainingRunRow,
    *REGISTERED_PRODUCTION_MODELS,
    ReconciliationRow,
    ReleaseRow,
    ReleaseEntryRow,
    AssetApplicationRow,
    AssetControlRow,
    AssetGrantRow,
    AssetUsageRow,
    DataAssetHistoryRow,
    DataAssetRow,
    AnnotationBatchRow,
    AnnotationSamplingRow,
    AnnotationInspectionRow,
    ActionAuditRow,
    ActionOperationRow,
    ActionPlanRow,
    ActionRunRow,
    ApprovalRow,
    CustomOperatorRow,
    CustomRunRow,
    DqRuleRow,
    DqHistoryRow,
    DqRunRow,
    DqResultRow,
    DqIssueRow,
    DqIssueAuditRow,
    DqWebhookRow,
    FileStateRow,
    FileDiscoveryRow,
    FileDiscoveryCheckpointRow,
    DatasheetJobRow,
    BudgetAccountRow,
    BudgetReservationRow,
    ConversationRequestRow,
    ConversationRow,
    ConversationResumeRow,
    ConversationAuditRow,
    EvalRunRow,
    KGEvalRunRow,
    KGCacheRow,
    KGRunRow,
    ModelCallTraceRow,
    MemoryRow,
    MemoryWriteRow,
    MemoryUseRow,
    MemoryAuditRow,
    ToolInvocationRow,
    TranscriptionRow,
    UploadRow,
    AssertionRow,
    AssertionDecisionRow,
    EvidenceCacheRow,
    CatalogObjectRow,
    CatalogEdgeRow,
    MetricAuditRow,
    AskConversationRow,
    AskSessionRow,
    AskAnswerRow,
    DatasheetRow,
    CheckpointRow,
    CheckpointWriteRow,
    WorkflowRunRow,
    WorkflowStepRow,
    WorkflowAuditRow,
    WorkflowResumeRow,
)

__all__ = [
    "install_asset_constraints",
    "install_evidence_constraints",
    "install_file_discovery",
    "install_llm_data_constraints",
    "install_production_schema",
    "install_release_constraints",
    "install_training_constraints",
]
