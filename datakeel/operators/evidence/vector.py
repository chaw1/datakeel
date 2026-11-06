# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare vector nodes whose only executable path is the signed fake worker."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.core.vector_models import ClusterParams, DuplicateParams, EmbedParams, VectorError
from datakeel.evidence.vector_parameters import CoverageParams
from datakeel.operators.base import Operator, OperatorResult, Params


class VectorEmbedParams(EmbedParams, Params):
    """Expose the fake embedding schema through the existing operator registry."""


class SemanticDuplicateParams(DuplicateParams, Params):
    """Expose bounded direct-pair parameters through the existing registry."""


class SemanticClusterParams(ClusterParams, Params):
    """Expose exact DBSCAN parameters through the signed pipeline registry."""


class CoverageGapParams(CoverageParams, Params):
    """Expose frozen relative reference selection without an automatic action."""


def _refuse(files: list[FileItem], directory: Path, params: Params) -> OperatorResult:
    del files, directory, params
    msg = "vector_requires_consumed_human_approval"
    raise VectorError(msg)


EMBED = Operator("evidence.vector_embed", "any", "evidence", VectorEmbedParams, _refuse)
DUPLICATE = Operator(
    "evidence.semantic_duplicate", "any", "evidence", SemanticDuplicateParams, _refuse
)

CLUSTER = Operator("evidence.semantic_cluster", "any", "evidence", SemanticClusterParams, _refuse)
OUTLIER = Operator("evidence.semantic_outlier", "any", "evidence", SemanticClusterParams, _refuse)
GAP = Operator("evidence.coverage_gap", "any", "evidence", CoverageGapParams, _refuse)
