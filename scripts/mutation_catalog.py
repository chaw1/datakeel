# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Feature mutation catalogs, run after the original guard mutations in this order."""

from scripts.advanced_mutations import ADVANCED_MUTATIONS
from scripts.annotation_qa_mutations import ANNOTATION_QA_MUTATIONS
from scripts.ask_chart_mutations import ASK_CHART_MUTATIONS
from scripts.auto_routing_mutations import AUTO_ROUTING_MUTATIONS
from scripts.coordinate_mutations import COORDINATE_MUTATIONS
from scripts.data_asset_mutations import DATA_ASSET_MUTATIONS
from scripts.datasheet_mutations import DATASHEET_MUTATIONS
from scripts.dq_mutations import DQ_MUTATIONS
from scripts.guard_mutations import GUARD_MUTATIONS
from scripts.image_kg_mutations import IMAGE_KG_MUTATIONS
from scripts.kg_mutations import KG_MUTATIONS
from scripts.knowledge_mutations import KNOWLEDGE_MUTATIONS
from scripts.llm_data_governance_mutations import LLM_DATA_GOVERNANCE_MUTATIONS
from scripts.llm_data_mutations import LLM_DATA_MUTATIONS
from scripts.llm_data_performance_mutations import LLM_DATA_PERFORMANCE_MUTATIONS
from scripts.llm_data_scale_mutations import LLM_DATA_SCALE_MUTATIONS
from scripts.media_mutations import MEDIA_MUTATIONS
from scripts.metadata_mutations import METADATA_MUTATIONS
from scripts.metric_mutations import METRIC_MUTATIONS
from scripts.orchestration_mutations import ORCHESTRATION_MUTATIONS
from scripts.pii_mutations import PII_MUTATIONS
from scripts.release_mutations import RELEASE_MUTATIONS
from scripts.sandbox_mutations import SANDBOX_MUTATIONS
from scripts.standard_mutations import LEXICAL_RULE_MUTATIONS, STANDARD_MUTATIONS
from scripts.table_mutations import TABLE_MUTATIONS
from scripts.text_dedup_mutations import TEXT_DEDUP_MUTATIONS
from scripts.timeseries_mutations import TIMESERIES_MUTATIONS
from scripts.training_hf_mutations import HF_TRAINING_MUTATIONS
from scripts.training_multilabel_mutations import TRAINING_MULTILABEL_MUTATIONS
from scripts.training_mutations import TRAINING_MUTATIONS
from scripts.training_source_mutations import TRAINING_SOURCE_MUTATIONS
from scripts.training_text_mutations import TRAINING_TEXT_MUTATIONS

FEATURE_MUTATIONS = (
    *ADVANCED_MUTATIONS,
    *KG_MUTATIONS,
    *KNOWLEDGE_MUTATIONS,
    *METRIC_MUTATIONS,
    *IMAGE_KG_MUTATIONS,
    *GUARD_MUTATIONS,
    *TIMESERIES_MUTATIONS,
    *TABLE_MUTATIONS,
    *AUTO_ROUTING_MUTATIONS,
    *COORDINATE_MUTATIONS,
    *RELEASE_MUTATIONS,
    *DATA_ASSET_MUTATIONS,
    *STANDARD_MUTATIONS,
    *LEXICAL_RULE_MUTATIONS,
    *DQ_MUTATIONS,
    *METADATA_MUTATIONS,
    *ORCHESTRATION_MUTATIONS,
    *ANNOTATION_QA_MUTATIONS,
    *DATASHEET_MUTATIONS,
    *ASK_CHART_MUTATIONS,
    *TRAINING_MUTATIONS,
    *HF_TRAINING_MUTATIONS,
    *TRAINING_MULTILABEL_MUTATIONS,
    *TRAINING_TEXT_MUTATIONS,
    *TRAINING_SOURCE_MUTATIONS,
    *MEDIA_MUTATIONS,
    *PII_MUTATIONS,
    *TEXT_DEDUP_MUTATIONS,
    *LLM_DATA_MUTATIONS,
    *LLM_DATA_PERFORMANCE_MUTATIONS,
    *LLM_DATA_SCALE_MUTATIONS,
    *LLM_DATA_GOVERNANCE_MUTATIONS,
    *SANDBOX_MUTATIONS,
)
