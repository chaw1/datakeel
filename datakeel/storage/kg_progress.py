# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recover terminal extraction accounting from committed progress and provider traces."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.harness_models import ModelCallTrace
from datakeel.core.kg_execution import KGJob, KGReport
from datakeel.kg.policy import is_external
from datakeel.storage.harness_rows import ModelCallTraceRow
from datakeel.storage.transcription_pricing import transcription_external


def failed_report(session: Session, job: KGJob, reason: str) -> KGReport:
    """Retain completed work and settled charges when the whole run cannot publish."""
    traces = [
        ModelCallTrace.model_validate(row.payload)
        for row in session.scalars(
            select(ModelCallTraceRow).where(ModelCallTraceRow.conversation_id == job.run.id)
        )
    ]
    usages = [trace.observed_usage or trace.usage for trace in traces]
    accounted = sum((trace.cost_usd for trace in traces), start=Decimal(0))
    cloud = [
        trace
        for trace in traces
        if (
            transcription_external(job.prepared.transcription_profile)
            if trace.call_type == "transcription" and job.prepared.transcription_profile
            else is_external(job.prepared.profile)
        )
    ]
    report = job.run.report
    completed = report.cached + report.extracted + report.failed
    return report.model_copy(
        update={
            "model_calls": len(traces),
            "transcription_cost_upper_usd": job.prepared.transcription_cost_upper_usd,
            "cloud_calls": len(cloud),
            "cloud_cost_usd": None
            if any(trace.billing_status == "unknown" for trace in cloud)
            else sum((trace.cost_usd for trace in cloud), start=Decimal(0)),
            "input_tokens": sum(usage.input_tokens for usage in usages),
            "output_tokens": sum(usage.output_tokens for usage in usages),
            "accounted_cost_usd": accounted,
            "cost_usd": None
            if any(trace.billing_status == "unknown" for trace in traces)
            else accounted,
            "unexecuted": max(
                0,
                sum(1 if item.image else len(item.blocks) for item in job.prepared.documents)
                - completed,
            ),
            "error": reason,
            "partial_documents": tuple(item.asset_ref.asset_id for item in job.prepared.documents),
        }
    )
