# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Native monitor failures must never authorize an unmeasured local worker."""

from scripts.mutation_models import Mutation

SANDBOX_MUTATIONS = (
    Mutation(
        name="sandbox-native-memory-fail-closed",
        path="operators/custom_memory.py",
        before="        raise RuntimeFailureError(msg) from error",
        after="        return False",
        case=(
            "tests/operators/custom_sandbox/test_subprocess.py::"
            "test_subprocess_unreadable_native_memory_fails_closed"
        ),
        runner="pytest",
    ),
)
