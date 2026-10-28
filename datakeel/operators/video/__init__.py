# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Video inspection, quality, deduplication and deterministic transformation operators."""

from datakeel.operators.video.dedup import OPERATOR as DEDUP
from datakeel.operators.video.invalid_frames import OPERATOR as INVALID_FRAMES
from datakeel.operators.video.normalize import OPERATOR as NORMALIZE
from datakeel.operators.video.probe import OPERATOR as PROBE
from datakeel.operators.video.segment import OPERATOR as SEGMENT

OPERATORS = (PROBE, INVALID_FRAMES, DEDUP, SEGMENT, NORMALIZE)
