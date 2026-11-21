# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect specialists and actor-owned conversations, or stream a controlled agent turn."""

import argparse
from collections.abc import Iterator
from typing import Literal

from pydantic import TypeAdapter
from rich.console import Console

from datakeel.agent.models import AgentEvent, ConversationView
from datakeel.cli.parsers import CommandGroup
from datakeel.core.agent_models import ConversationCreate, MessageInput, Provider, ResumeInput
from datakeel.core.models import BoundaryModel, new_id
from datakeel.delegation.loader import is_read_only_agent, list_agents
from datakeel.delegation.models import AgentDefinition
from datakeel.delegation.tree import call_tree
from datakeel.storage.database import Database
from datakeel.storage.identity_sessions import require_session_actor


class _Specialist(AgentDefinition):
    read_only: bool


class _Summary(BoundaryModel):
    id: str
    model: str
    turns: int
    pending_plans: int
    dataset_id: str | None
    preview: str


class _Turn(BoundaryModel):
    conversation_id: str
    mode: Literal["auto", "plan", "agent"]
    events: list[AgentEvent]


def register_parser(commands: CommandGroup) -> None:
    """Register specialist discovery, history, telemetry and conversation commands."""
    group = commands.add_parser("agent")
    subcommands = group.add_subparsers(dest="agent_command", required=True)
    for name in ("specialists", "list", "tree", "chat", "resume"):
        sub = subcommands.add_parser(name)
        sub.add_argument("--json", action="store_true", dest="json_output")
        if name != "specialists":
            sub.add_argument("--actor", default="local")
        if name in {"list", "chat"}:
            sub.add_argument("--dataset")
        if name in {"tree", "resume"}:
            sub.add_argument("conversation_id")
        if name == "list":
            sub.add_argument("--q")
        elif name == "chat":
            sub.add_argument("message")
            sub.add_argument("--conversation")
            sub.add_argument("--mode", choices=("auto", "plan", "agent"), default="auto")
            sub.add_argument("--dry-run", action="store_true")
        elif name == "resume":
            sub.add_argument("--plan", required=True)


def _specialists(args: argparse.Namespace, console: Console) -> None:
    items = [
        _Specialist(**item.model_dump(), read_only=is_read_only_agent(item))
        for item in list_agents()
    ]
    if args.json_output:
        console.print(TypeAdapter(list[_Specialist]).dump_json(items, indent=2).decode())
        return
    for item in items:
        console.print(
            f"{item.name}  read_only={item.read_only}  max_turns={item.max_turns}\n"
            f"  {item.description}\n  Tools: {', '.join(item.tools)}"
        )


def _search_text(conversation: ConversationView) -> str:
    parts = [conversation.id, conversation.config.dataset_id or "", conversation.config.model]
    for message in conversation.messages:
        if message.role in {"user", "assistant"}:
            parts.append(message.content)
        parts.extend(call.name for call in message.tool_calls)
        parts.append(message.name or "")
    for event in conversation.events:
        if event.call is not None:
            parts.append(event.call.name)
        if event.outcome is not None:
            parts.append(event.outcome.name)
        if event.intent is not None:
            parts.extend((event.intent.text, event.intent.request, event.intent.kind))
    return " ".join(parts).casefold()


def _summary(conversation: ConversationView) -> _Summary:
    preview = next(
        (
            message.content
            for message in reversed(conversation.messages)
            if message.role in {"user", "assistant"} and message.content
        ),
        "",
    )
    return _Summary(
        id=conversation.id,
        model=conversation.config.model,
        turns=conversation.turns,
        pending_plans=len(conversation.pending_plans),
        dataset_id=conversation.config.dataset_id,
        preview=" ".join(preview.split())[:120],
    )


def _list(db: Database, args: argparse.Namespace, console: Console) -> None:
    from datakeel.agent.service import list_conversations  # noqa: PLC0415

    terms = (args.q or "").casefold().split()
    items = [
        _summary(item)
        for item in list_conversations(db, actor=args.actor)
        if (args.dataset is None or item.config.dataset_id == args.dataset)
        and all(term in _search_text(item) for term in terms)
    ]
    if args.json_output:
        console.print(TypeAdapter(list[_Summary]).dump_json(items, indent=2).decode())
    elif not items:
        console.print("No conversations found.")
    else:
        for item in items:
            console.print(
                f"{item.id}  model={item.model}  turns={item.turns}  "
                f"pending_plans={item.pending_plans}  dataset_id={item.dataset_id or '-'}\n"
                f"  {item.preview}"
            )


def _tree(db: Database, args: argparse.Namespace, console: Console) -> None:
    require_session_actor(db, args.conversation_id, args.actor)
    tree = call_tree(db, args.conversation_id)
    if args.json_output:
        console.print(tree.model_dump_json(indent=2))
        return
    console.print(
        f"total_tokens={tree.total_tokens}  total_cost_usd={tree.total_cost_usd}\n"
        f"total_tool_calls={tree.total_tool_calls}  "
        f"total_tool_elapsed_ms={tree.total_tool_elapsed_ms}\n"
        f"Models: {', '.join(tree.models) or '-'}"
    )
    for node in tree.nodes:
        console.print(
            f"{'  ' * node.depth}agent_path={node.agent_path}  "
            f"agent_name={node.agent_name}  id={node.id}\n"
            f"  tokens={node.tokens}  cost_usd={node.cost_usd}  model_calls={node.model_calls}  "
            f"tool_elapsed_ms={node.tool_elapsed_ms}  failed_tools={node.failed_tools}\n"
            f"  Tools: {', '.join(node.tools) or '-'}"
        )


def _event_line(event: AgentEvent) -> str | None:
    if event.event == "tool_call" and event.call is not None:
        return f"Tool call: {event.call.name} ({event.call.id})"
    if event.event == "tool_result" and event.outcome is not None:
        outcome = event.outcome
        return f"Tool result: {outcome.name} {outcome.status} {outcome.error or ''}".rstrip()
    if event.event == "plan" and event.outcome is not None and event.outcome.plan is not None:
        plan = event.outcome.plan
        return f"Plan: {plan.id} {plan.action_type} requires_approval={plan.requires_approval}"
    if event.event == "receipt" and event.outcome is not None and event.outcome.run is not None:
        return f"Receipt: {event.outcome.run.id} {event.outcome.run.status}"
    if event.event == "intent" and event.intent is not None:
        return f"Intent: {event.intent.kind} {event.intent.text}"
    return (
        f"Stopped: {event.stop_reason or ''} {event.text or ''}".rstrip()
        if event.event == "stopped"
        else None
    )


class _Stream:
    def __init__(self, console: Console) -> None:
        self.console = console
        self.streamed: set[str] = set()
        self.open_line = False

    def newline(self) -> None:
        if self.open_line:
            self.console.print()
            self.open_line = False

    def show(self, event: AgentEvent) -> None:
        if event.event == "text_delta":
            if event.text == "":
                self.newline()
                self.streamed.discard(event.agent_path)
            if event.text:
                self.console.print(event.text, end="")
                self.streamed.add(event.agent_path)
                self.open_line = not event.text.endswith("\n")
            return
        if event.event == "text":
            self.newline()
            if event.agent_path not in self.streamed and event.text:
                self.console.print(event.text)
            self.streamed.discard(event.agent_path)
            return
        line = _event_line(event)
        if line is not None:
            self.newline()
            self.console.print(line)


def _report_turn(
    events: Iterator[AgentEvent],
    conversation_id: str,
    mode: Literal["auto", "plan", "agent"],
    *,
    json_output: bool,
    console: Console,
) -> None:
    if json_output:
        turn = _Turn(
            conversation_id=conversation_id,
            mode=mode,
            events=[event for event in events if event.event != "text_delta"],
        )
        console.print(turn.model_dump_json(indent=2))
        return
    stream = _Stream(console)
    for event in events:
        stream.show(event)
    stream.newline()
    console.print(f"Conversation: {conversation_id}")


def dispatch(db: Database, args: argparse.Namespace, provider: Provider | None = None) -> None:
    """Use native services and an optional provider for deterministic offline conversations."""
    console = Console(markup=False, highlight=False, soft_wrap=True)
    if args.agent_command == "specialists":
        _specialists(args, console)
    elif args.agent_command == "list":
        _list(db, args, console)
    elif args.agent_command == "tree":
        _tree(db, args, console)
    else:
        _chat(db, args, provider, console)


def _chat(
    db: Database, args: argparse.Namespace, provider: Provider | None, console: Console
) -> None:
    # Load model adapters only when a conversation command needs them.
    from datakeel.agent import service  # noqa: PLC0415

    if args.agent_command == "resume":
        identifier = args.conversation_id
        mode = "agent"
        events = service.resume_conversation(
            db,
            identifier,
            ResumeInput(plan_id=args.plan, idempotency_key=new_id()),
            actor=args.actor,
            provider=provider,
        )
    else:
        identifier = args.conversation
        if identifier is None:
            defaults = service.conversation_defaults()
            identifier = service.create_conversation(
                db,
                ConversationCreate(
                    provider=defaults.provider,
                    model=defaults.model,
                    dataset_id=args.dataset,
                    dry_run=args.dry_run,
                ),
                actor=args.actor,
            ).id
        request = MessageInput(content=args.message, mode=args.mode)
        mode = request.mode
        events = service.send_message(db, identifier, request, actor=args.actor, provider=provider)
    _report_turn(events, identifier, mode, json_output=args.json_output, console=console)
