# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Durable local conversations and server-sent model/tool/action events."""

import re
from collections.abc import Generator, Iterator
from datetime import datetime
from html import escape
from itertools import chain
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import JsonValue
from starlette.background import BackgroundTask

from datakeel.agent import service
from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.api.dependencies import DatabaseDependency
from datakeel.api.identity_access import http_actor
from datakeel.core.agent_models import (
    ConversationAudit,
    ConversationCreate,
    ConversationDefaults,
    MessageInput,
    Provider,
    ResumeInput,
)
from datakeel.core.models import BoundaryModel, utcnow
from datakeel.core.pii import redact_pii
from datakeel.core.routing_models import RouteDecision
from datakeel.delegation.loader import list_agents
from datakeel.delegation.models import AgentDefinition, CallTree
from datakeel.delegation.tree import call_tree
from datakeel.storage.conversation_authorization import list_audit
from datakeel.storage.identity_sessions import require_session_actor

router = APIRouter(prefix="/api/agent/conversations", tags=["agent"])


class ConversationReport(BoundaryModel):
    """Export authorized conversation evidence and its measured execution tree."""

    conversation: ConversationView
    call_tree: CallTree
    exported_at: datetime


class EventStreamResponse(StreamingResponse):
    """Declare the streaming media type alongside its typed event schema."""

    media_type = "text/event-stream"


def get_provider(request: Request) -> Provider | None:
    """Resolve an explicitly injected test provider, otherwise use session settings."""
    return cast("Provider | None", getattr(request.app.state, "agent_provider", None))


ProviderDependency = Annotated[Provider | None, Depends(get_provider)]


@router.post("")
def create(body: ConversationCreate, db: DatabaseDependency, request: Request) -> ConversationView:
    """Create a session with persistent limits and optional dataset context."""
    return service.create_conversation(db, body, actor=http_actor(request))


@router.get("")
def list_all(
    db: DatabaseDependency, request: Request, q: str | None = None, dataset_id: str | None = None
) -> list[ConversationView]:
    """List recoverable local conversations."""
    return _filter_conversations(
        service.list_conversations(db, actor=http_actor(request)), q=q, dataset_id=dataset_id
    )


def _filter_conversations(
    items: list[ConversationView], *, q: str | None, dataset_id: str | None
) -> list[ConversationView]:
    """Search already authorized transcripts without changing their established order."""
    tokens = (q or "").casefold().split()
    dataset_id = (dataset_id or "").strip()
    if not tokens and not dataset_id:
        return items
    matches: list[ConversationView] = []
    for item in items:
        if dataset_id and item.config.dataset_id != dataset_id:
            continue
        fields = [item.id, item.config.dataset_id or "", item.config.model]
        fields.extend(
            message.content for message in item.messages if message.role in {"user", "assistant"}
        )
        fields.extend(call.name for message in item.messages for call in message.tool_calls)
        fields.extend(event.call.name for event in item.events if event.call is not None)
        fields.extend(
            text
            for event in item.events
            if event.intent is not None
            for text in (event.intent.text, event.intent.request, event.intent.kind)
        )
        searchable = "\n".join(fields).casefold()
        if all(token in searchable for token in tokens):
            matches.append(item)
    return matches


@router.get("/{conversation_id}")
def get(conversation_id: str, db: DatabaseDependency, request: Request) -> ConversationView:
    """Recover all persisted events and current human approval decisions."""
    return service.get_conversation(db, conversation_id, actor=http_actor(request))


@router.get("/{conversation_id}/tree")
def tree(conversation_id: str, db: DatabaseDependency, request: Request) -> CallTree:
    """Read nested specialist sessions and every metered parent and child call."""
    require_session_actor(db, conversation_id, http_actor(request))
    return call_tree(db, conversation_id)


@router.get(
    "/{conversation_id}/export",
    response_model=ConversationReport,
    responses={200: {"content": {"text/markdown": {"schema": {"type": "string"}}}}},
)
def export_conversation(
    conversation_id: str,
    db: DatabaseDependency,
    request: Request,
    export_format: Annotated[Literal["markdown", "json"], Query(alias="format")] = "markdown",
) -> Response:
    """Download current authorized evidence without querying private session secrets."""
    conversation = service.get_conversation(db, conversation_id, actor=http_actor(request))
    report = ConversationReport(
        conversation=conversation, call_tree=call_tree(db, conversation_id), exported_at=utcnow()
    )
    report = ConversationReport.model_validate(_redact_report(report.model_dump(mode="json")))
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", conversation.id)[:128] or "session"
    suffix = "json" if export_format == "json" else "md"
    headers = {
        "Content-Disposition": f'attachment; filename="datakeel-conversation-{safe_id}.{suffix}"'
    }
    if export_format == "json":
        return Response(
            report.model_dump_json(indent=2), media_type="application/json", headers=headers
        )
    return PlainTextResponse(
        _report_markdown(report), media_type="text/markdown; charset=utf-8", headers=headers
    )


def _redact_report(value: JsonValue, label: str | None = None) -> JsonValue:
    if isinstance(value, str):
        safe = redact_pii(value, kinds=frozenset({"secret", "credential_url"}), label=label)
        return re.sub(r"(?i)d\s*k\s*c\s*_\s*(?:[0-9a-f]\s*){24}", "[REDACTED]", safe)
    if isinstance(value, list):
        return [_redact_report(item, label) for item in value]
    if isinstance(value, dict):
        return {
            cast("str", _redact_report(key)): _redact_report(item, key)
            for key, item in value.items()
        }
    return value


def _cell(value: object) -> str:
    return escape(str(value)).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def _report_markdown(report: ConversationReport) -> str:
    conversation, config = report.conversation, report.conversation.config
    metadata = {
        "id": conversation.id,
        "model": config.model,
        "provider": config.provider,
        "dataset_id": config.dataset_id,
        "dry_run": config.dry_run,
        "turns": conversation.turns,
        "created_at": conversation.created_at.isoformat(),
        "exported_at": report.exported_at.isoformat(),
        "budget": config.budget.model_dump_json(),
    }
    lines = ["# Datakeel Conversation Report", "", "## Session Metadata", ""]
    lines.extend(f"- {key}: {_cell(value)}" for key, value in metadata.items())
    lines.extend(_telemetry_markdown(report.call_tree))
    lines.extend(_actions_markdown(conversation.events))
    lines.extend(_transcript_markdown(conversation))
    return "\n".join(lines) + "\n"


def _telemetry_markdown(tree: CallTree) -> list[str]:
    lines = ["", "## Execution & Cost Telemetry", ""]
    lines.extend(
        f"- {key}: {_cell(value)}"
        for key, value in tree.model_dump(
            exclude={"nodes", "traces", "models", "total_cost_usd"}
        ).items()
    )
    lines.extend(
        [
            f"- total_cost_usd: {tree.total_cost_usd:f}",
            f"- models: {_cell(', '.join(tree.models))}",
            "",
            (
                "| Agent | Path | Tokens | Cost (USD) | Model calls | Tool latency (ms) | "
                "Failed tools | Tools |"
            ),
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for node in tree.nodes:
        cells = (
            node.agent_name,
            node.agent_path,
            node.tokens,
            f"{node.cost_usd:f}",
            node.model_calls,
            node.tool_elapsed_ms,
            node.failed_tools,
            ", ".join(node.tools),
        )
        lines.append("| " + " | ".join(_cell(value) for value in cells) + " |")
    return lines


def _actions_markdown(events: list[AgentEvent]) -> list[str]:
    lines: list[str] = []
    for event in events:
        if event.event not in {"plan", "receipt"} or event.outcome is None:
            continue
        outcome = event.outcome
        if outcome.plan is not None:
            plan = outcome.plan
            lines.append(
                f"- plan.id: {_cell(plan.id)}; action_type: {_cell(plan.action_type)}; "
                f"status: {plan.status}; requires_approval: {plan.requires_approval}"
            )
        if outcome.run is not None:
            lines.append(f"- run.id: {_cell(outcome.run.id)}; run.status: {outcome.run.status}")
    return ["", "## Action Plans & Receipts", "", *lines] if lines else []


def _event_markdown(event: AgentEvent) -> list[str]:
    lines: list[str] = []
    if event.text and event.event != "text_delta":
        lines.append(f"Assistant ({event.agent_path}): {event.text}")
    if event.call is not None:
        lines.append(f"Tool call ({event.agent_path}): {event.call.name}; id: {event.call.id}")
    if event.outcome is not None:
        outcome = event.outcome
        lines.append(f"Tool result ({event.agent_path}): {outcome.name}; status: {outcome.status}")
        if outcome.error:
            lines.append(f"Error: {outcome.error}")
    if event.intent is not None:
        lines.append(f"Intent ({event.intent.kind}): {event.intent.text}")
    if event.stop_reason:
        lines.append(f"Stop reason ({event.agent_path}): {event.stop_reason}")
    return lines


def _transcript_markdown(conversation: ConversationView) -> list[str]:
    lines = ["", "## Chronological Transcript", ""]
    if not conversation.events:
        entries = [
            f"{message.role.title()}: {message.content}"
            for message in conversation.messages
            if message.role in {"user", "assistant"}
        ]
    else:
        groups: list[list[AgentEvent]] = [[]]
        for event in conversation.events:
            root = event.agent_path == "main"
            # Approval continuation starts with a receipt and has no new user message.
            if root and event.event == "receipt" and len(groups) > 1 and not groups[-1]:
                groups.pop()
            groups[-1].append(event)
            if root and event.event == "done":
                groups.append([])
        users = [message.content for message in conversation.messages if message.role == "user"]
        if len([group for group in groups if group]) > len(users):
            # Failed resumes have no receipt or durable user-turn identifier to align by.
            lines.extend(
                [
                    "Turn correlation unavailable; each sequence retains its recorded order.",
                    "",
                    "### Messages",
                    "",
                    *[
                        f"> {escape(line)}"
                        for message in conversation.messages
                        if message.role in {"user", "assistant"}
                        for line in f"{message.role.title()}: {message.content}".splitlines()
                    ],
                    "",
                    "### Execution events",
                    "",
                ]
            )
            users = []
        entries: list[str] = []
        for index in range(max(len(users), len(groups))):
            if index < len(users):
                entries.append(f"User: {users[index]}")
            if index < len(groups):
                entries.extend(line for event in groups[index] for line in _event_markdown(event))
    for entry in entries:
        lines.extend([*(f"> {escape(line)}" for line in entry.splitlines()), ""])
    return lines


@router.get("/definitions/provider")
def provider_defaults() -> ConversationDefaults:
    """The model new conversations use: the configured one, or the offline demo without keys."""
    return service.conversation_defaults()


@router.get("/definitions/agents")
def definitions() -> list[AgentDefinition]:
    """List validated specialist contracts bundled with this installation."""
    return list_agents()


def _encode(events: Iterator[AgentEvent], first: AgentEvent | None) -> Iterator[str]:
    for event in chain([first] if first is not None else [], events):
        yield f"id: {event.id}\nevent: {event.event}\ndata: {event.model_dump_json()}\n\n"


@router.post(
    "/{conversation_id}/messages", response_model=AgentEvent, response_class=EventStreamResponse
)
def send(
    conversation_id: str,
    body: MessageInput,
    db: DatabaseDependency,
    provider: ProviderDependency,
    request: Request,
) -> EventStreamResponse:
    """Stream durable events with explicit replay keys and no duplicate execution."""
    stream = cast(
        "Generator[AgentEvent, None, None]",
        service.send_message(
            db, conversation_id, body, provider=provider, actor=http_actor(request)
        ),
    )
    first = next(stream, None)
    return EventStreamResponse(
        _encode(stream, first),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(stream.close),
    )


@router.post(
    "/{conversation_id}/resume", response_model=AgentEvent, response_class=EventStreamResponse
)
def resume(
    conversation_id: str,
    body: ResumeInput,
    db: DatabaseDependency,
    provider: ProviderDependency,
    request: Request,
) -> EventStreamResponse:
    """Continue an approved pause without treating caller input as execution authority."""
    stream = cast(
        "Generator[AgentEvent, None, None]",
        service.resume_conversation(
            db, conversation_id, body, provider=provider, actor=http_actor(request)
        ),
    )
    first = next(stream, None)
    return EventStreamResponse(
        _encode(stream, first),
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(stream.close),
    )


@router.get("/{conversation_id}/audit")
def recovery_audit(
    conversation_id: str, db: DatabaseDependency, request: Request
) -> list[ConversationAudit]:
    """Read persisted resume denials, authorization checks and pause invalidations."""
    require_session_actor(db, conversation_id, http_actor(request))
    return list_audit(db, conversation_id)


@router.get("/{conversation_id}/routes")
def routes(conversation_id: str, db: DatabaseDependency, request: Request) -> list[RouteDecision]:
    """Read persisted workflow suggestions and free-Agent routing decisions."""
    return [
        event.route
        for event in service.get_conversation(db, conversation_id, actor=http_actor(request)).events
        if event.route is not None
    ]
