# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""K9 export, build, and read-only boundary anchors with exact regression targets."""

from scripts.mutation_models import Mutation

_OTEL = "tests/harness/test_otel.py::"
_HTTP = "tests/harness/test_otel_http.py::"
_CLI = "tests/cli/test_otel_export.py::"
_BUILD = "tests/test_build_local.py::"

K9_MUTATIONS = (
    Mutation(
        name="otel-operation-name",
        path="harness/otel.py",
        before='"gen_ai.operation.name": "chat",',
        after='"gen_ai.operation.name": "generate_content",',
        case=_OTEL
        + "test_mapping_when_conversation_has_usage_preserves_dual_semantics_and_approximate_time",
        runner="pytest",
    ),
    Mutation(
        name="otel-observed-usage",
        path="harness/otel.py",
        before="usage = item.observed_usage or item.usage",
        after="usage = item.usage",
        case=_OTEL + "test_usage_when_unknown_has_observed_usage_exports_observation_not_accounted",
        runner="pytest",
    ),
    Mutation(
        name="otel-unknown-zero-usage",
        path="harness/otel.py",
        before='if item.billing_status == "actual" or item.observed_usage is not None:',
        after="if True:",
        case=_OTEL + "test_usage_when_unknown_without_observation_omits_usage_and_zero_cache",
        runner="pytest",
    ),
    Mutation(
        name="otel-span-start",
        path="harness/otel.py",
        before="return max(0, end - _nanoseconds(item.latency_ms)), end",
        after="return end, end",
        case=_OTEL
        + "test_mapping_when_conversation_has_usage_preserves_dual_semantics_and_approximate_time",
        runner="pytest",
    ),
    Mutation(
        name="otel-openinference-kind",
        path="harness/otel.py",
        before='"openinference.span.kind": "LLM",',
        after='"openinference.span.kind": "CHAIN",',
        case=_OTEL
        + "test_mapping_when_conversation_has_usage_preserves_dual_semantics_and_approximate_time",
        runner="pytest",
    ),
    Mutation(
        name="otel-secret-boundary",
        path="harness/otel.py",
        before='"datakeel.stop_reason": item.stop_reason,',
        after=(
            '"datakeel.stop_reason": item.stop_reason,\n'
            '        "gen_ai.prompt": os.environ.get("OTEL_EXPORTER_OTLP_TRACES_HEADERS", ""),'
        ),
        case=_OTEL + "test_attribute_keys_when_sensitive_fields_exist_use_exact_allowlist",
        runner="pytest",
    ),
    Mutation(
        name="wheel-required-notices",
        path="scripts/build_wheel.py",
        before="if package not in notices:",
        after="if False:",
        case=_BUILD + "test_wheel_validation_when_notices_stale_fails",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="docker-local-only",
        path="scripts/build_image.py",
        before='"docker",\n        "build",',
        after='"docker",\n        "build",\n        "--push",',
        case=_BUILD + "test_docker_build_command_when_called_is_local_build_only",
        runner="pytest",
        source_root="repository",
    ),
    Mutation(
        name="otel-export-result-dropped",
        path="harness/otel_checked.py",
        before="if result is SpanExportResult.SUCCESS:",
        after="if True:",
        case=_OTEL + "test_processor_when_export_fails_or_raises_never_reports_accepted",
        runner="pytest",
    ),
    Mutation(
        name="otel-partial-success",
        path="harness/otel_checked.py",
        before="if rejected:",
        after="if False:",
        case=_HTTP + "test_http_when_200_rejects_spans_fails_once_without_retry",
        runner="pytest",
    ),
    Mutation(
        name="otel-http-200-only",
        path="harness/otel_checked.py",
        before="if result.status_code != _HTTP_OK:",
        after="if False:",
        case=_HTTP + "test_http_when_status_is_not_200_fails_without_successful_retry[204]",
        runner="pytest",
    ),
    Mutation(
        name="otel-queue-drop",
        path="harness/otel_checked.py",
        before="if len(self._pending) == _BATCH_SIZE:",
        after="if False:",
        case=_OTEL + "test_processor_when_more_than_2048_spans_exports_every_bounded_batch",
        runner="pytest",
    ),
    Mutation(
        name="otel-nonconversation-session",
        path="harness/otel.py",
        before="if item.call_type in _CONVERSATION_CALLS:",
        after="if True:",
        case=_OTEL
        + "test_mapping_when_run_or_plan_has_no_fake_official_session"
        + "[extraction-main-datakeel.run.id]",
        runner="pytest",
    ),
    Mutation(
        name="otel-readonly-no-migrate",
        path="cli/__init__.py",
        before="db = Database(read_only=True)",
        after="db = Database()",
        case=_CLI + "test_export_traces_when_empty_dispatches_read_only_before_migrate",
        runner="pytest",
    ),
)
