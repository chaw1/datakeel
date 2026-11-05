# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Declare vector nodes whose only executable path is the signed fake worker."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.core.vector_models import DuplicateParams, EmbedParams, VectorError
from datakeel.operators.base import Operator, OperatorResult, Params


class VectorEmbedParams(EmbedParams, Params):
    """Expose the fake embedding schema through the existing operator registry."""


class SemanticDuplicateParams(DuplicateParams, Params):
    """Expose bounded direct-pair parameters through the existing registry."""


def _refuse(files: list[FileItem], directory: Path, params: Params) -> OperatorResult:
    del files, directory, params
    msg = "vector_requires_consumed_human_approval"
    raise VectorError(msg)


EMBED = Operator("evidence.vector_embed", "any", "evidence", VectorEmbedParams, _refuse)
DUPLICATE = Operator(
    "evidence.semantic_duplicate", "any", "evidence", SemanticDuplicateParams, _refuse
)
