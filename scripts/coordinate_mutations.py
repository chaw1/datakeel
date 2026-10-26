# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure coordinate interpretation and structured-output safety against regressions."""

from scripts.mutation_models import Mutation

_STRUCTURED = "tests/transcription/test_structured_coordinates.py::"

COORDINATE_MUTATIONS = (
    Mutation(
        name="normalized-coordinates-treated-as-pixels",
        path="core/transcription_coordinates.py",
        before='divisor = 1000 if coordinate_space == "normalized_1000" else 1',
        after="divisor = 1",
        case=_STRUCTURED + "test_normalized_1000_output_uses_original_image_pixels",
        runner="pytest",
    ),
    Mutation(
        name="coordinate-convention-omitted-from-cache",
        path="transcription/cache.py",
        before='data["model"] = profile.model',
        after='data.pop("coordinate_space", None)\n    data["model"] = profile.model',
        case="tests/transcription/test_coordinate_profile.py::"
        "test_digest_when_coordinate_semantics_change_requires_new_identity[change0]",
        runner="pytest",
    ),
    Mutation(
        name="visual-extra-fields-discard-line-text",
        path="core/transcription_coordinates.py",
        before='model_config = ConfigDict(extra="ignore", frozen=True)',
        after='model_config = ConfigDict(extra="forbid", frozen=True)',
        case=_STRUCTURED + "test_unknown_line_fields_are_counted_and_cannot_discard_readable_text",
        runner="pytest",
    ),
    Mutation(
        name="visual-malformed-envelope-leaks-raw-json",
        path="core/transcription_coordinates.py",
        before='text="\\n".join(words),',
        after='text="\\n".join(words) if words else text,',
        case=(
            _STRUCTURED + "test_unparseable_structured_output_never_publishes_raw_json"
            '[{"text":"unexpected envelope"}]'
        ),
        runner="pytest",
    ),
    Mutation(
        name="visual-ocr-coordinate-crosscheck-disabled",
        path="transcription/coordinates.py",
        before="if overlaps and median(overlaps) < threshold:",
        after="if False:",
        case="tests/transcription/test_coordinate_check.py::"
        "test_coordinate_check_when_median_low_discards_every_visual_box",
        runner="pytest",
    ),
)
