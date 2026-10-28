# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local deterministic audio inspection, quality and transformation operators."""

from datakeel.operators.audio.clipping import OPERATOR as CLIPPING
from datakeel.operators.audio.dedup import OPERATOR as DEDUP
from datakeel.operators.audio.loudness import OPERATOR as LOUDNESS
from datakeel.operators.audio.probe import OPERATOR as PROBE
from datakeel.operators.audio.trim_silence import OPERATOR as TRIM_SILENCE
from datakeel.operators.audio.vad import OPERATOR as VAD

OPERATORS = (PROBE, VAD, TRIM_SILENCE, LOUDNESS, CLIPPING, DEDUP)
