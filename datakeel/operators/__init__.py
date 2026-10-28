# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The complete phase-one operator registry; manifests derive from typed parameters."""

from datakeel.operators.base import Operator, OperatorManifest, OperatorResult
from datakeel.operators.evidence.annotation_labels import OPERATOR as ANNOTATION_LABELS
from datakeel.operators.evidence.caption_mentions import OPERATOR as CAPTION_MENTIONS
from datakeel.operators.evidence.image_phash import OPERATOR as IMAGE_PHASH
from datakeel.operators.evidence.label_gap import OPERATOR as LABEL_GAP
from datakeel.operators.evidence.near_duplicate import OPERATOR as NEAR_DUPLICATE
from datakeel.operators.file.corrupt_check import OPERATOR as CORRUPT_CHECK
from datakeel.operators.file.dedup import OPERATOR as FILE_DEDUP
from datakeel.operators.file.empty_check import OPERATOR as EMPTY_CHECK
from datakeel.operators.image.convert import OPERATOR as CONVERT
from datakeel.operators.image.quality import OPERATOR as IMAGE_QUALITY
from datakeel.operators.image.resize import OPERATOR as RESIZE
from datakeel.operators.image.thumbnail import OPERATOR as THUMBNAIL
from datakeel.operators.table.profile import OPERATOR as TABLE_PROFILE
from datakeel.operators.text.dedup import OPERATOR as TEXT_DEDUP
from datakeel.operators.text.encoding_fix import OPERATOR as ENCODING_FIX
from datakeel.operators.text.pii_redact import OPERATOR as PII_REDACT
from datakeel.operators.text.quality import OPERATOR as TEXT_QUALITY
from datakeel.operators.text.training_quality import OPERATOR as TRAINING_QUALITY
from datakeel.operators.timeseries.anomaly import OPERATOR as SERIES_ANOMALY
from datakeel.operators.timeseries.gaps import OPERATOR as SERIES_GAPS
from datakeel.operators.timeseries.order_dedup import OPERATOR as SERIES_ORDER
from datakeel.operators.timeseries.resample import OPERATOR as SERIES_RESAMPLE
from datakeel.operators.timeseries.timestamp_normalize import OPERATOR as SERIES_TIMESTAMP
from datakeel.operators.timeseries.unit_check import OPERATOR as SERIES_UNITS

REGISTRY: dict[str, Operator] = {
    operator.manifest.id: operator
    for operator in [
        FILE_DEDUP,
        CORRUPT_CHECK,
        EMPTY_CHECK,
        IMAGE_QUALITY,
        RESIZE,
        THUMBNAIL,
        CONVERT,
        ENCODING_FIX,
        PII_REDACT,
        TEXT_DEDUP,
        TEXT_QUALITY,
        TRAINING_QUALITY,
        IMAGE_PHASH,
        CAPTION_MENTIONS,
        ANNOTATION_LABELS,
        LABEL_GAP,
        NEAR_DUPLICATE,
        TABLE_PROFILE,
        SERIES_TIMESTAMP,
        SERIES_ORDER,
        SERIES_GAPS,
        SERIES_RESAMPLE,
        SERIES_ANOMALY,
        SERIES_UNITS,
    ]
}


def manifests() -> list[OperatorManifest]:
    """List schemas for every registered operator."""
    return [operator.manifest for operator in REGISTRY.values()]


__all__ = ["REGISTRY", "Operator", "OperatorManifest", "OperatorResult", "manifests"]
