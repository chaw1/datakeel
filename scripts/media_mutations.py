# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Audio streaming boundaries retain sample carries and MFCC frame overlap."""

from scripts.mutation_models import Mutation

MEDIA_MUTATIONS = (
    Mutation(
        name="audio-stream-partial-frame-carry-omitted",
        path="operators/audio/common.py",
        before="pending = samples[count * frame_size :].copy()",
        after="pending = np.empty(0, dtype=np.float64)",
        case=(
            "tests/operators/audio/test_streaming.py::"
            "test_activity_carries_partial_frames_across_decode_blocks"
        ),
        runner="pytest",
    ),
    Mutation(
        name="audio-stream-mfcc-preemphasis-overlap-omitted",
        path="operators/audio/fingerprint.py",
        before="samples[1:] - 0.97 * samples[:-1]\n            if start",
        after="np.append(samples[1], samples[2:] - 0.97 * samples[1:-1])\n            if start",
        case=(
            "tests/operators/audio/test_streaming.py::"
            "test_fingerprint_preserves_preemphasis_overlap_and_global_floor"
        ),
        runner="pytest",
    ),
)
