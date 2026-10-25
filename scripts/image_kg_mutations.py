# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Image graph guard mutations preserve the existing mutation corpus unchanged."""

from scripts.mutation_models import Mutation

IMAGE_KG_MUTATIONS = (
    Mutation(
        name="image-location-always-verified",
        path="evidence/kg_images.py",
        before="if not regions:",
        after="if False:",
        case="tests/harness/test_image_kg_mutations.py::test_image_without_ocr_regions_stays_a_review_candidate",
        runner="pytest",
    ),
    Mutation(
        name="transcription-quality-silent-pass",
        path="transcription/quality.py",
        before="if issues:",
        after="if False:",
        case="tests/harness/test_image_kg_mutations.py::test_transcription_truncation_cannot_silently_pass",
        runner="pytest",
    ),
    Mutation(
        name="transcription-cache-model-omitted",
        path="transcription/cache.py",
        before='data["model"] = profile.model',
        after='data["model"] = "omitted"',
        case="tests/harness/test_image_kg_mutations.py::test_transcription_model_participates_in_cache_identity",
        runner="pytest",
    ),
)
