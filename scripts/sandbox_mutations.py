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
    Mutation(
        name="sandbox-native-memory-exit-wait",
        path="operators/custom_memory.py",
        before="        process.wait(timeout=_EXIT_GRACE_SECONDS)",
        after="        raise subprocess.TimeoutExpired('owned-worker', _EXIT_GRACE_SECONDS)",
        case=(
            "tests/operators/custom_sandbox/test_memory.py::"
            "test_worker_exit_during_native_exception_is_not_monitor_failure"
        ),
        runner="pytest",
    ),
    Mutation(
        name="sandbox-native-memory-live-after-exit-wait",
        path="operators/custom_memory.py",
        before="    except subprocess.TimeoutExpired:\n        return False",
        after="    except subprocess.TimeoutExpired:\n        return True",
        case=(
            "tests/operators/custom_sandbox/test_memory.py::"
            "test_live_worker_native_exception_fails_closed"
        ),
        runner="pytest",
    ),
    Mutation(
        name="sandbox-completed-group-cleanup-denial",
        path="operators/custom_subprocess.py",
        before="except (PermissionError, ProcessLookupError):",
        after="except ProcessLookupError:",
        case=(
            "tests/operators/custom_sandbox/test_subprocess.py::"
            "test_subprocess_completed_worker_cleanup_denial_preserves_result"
        ),
        runner="pytest",
    ),
)
