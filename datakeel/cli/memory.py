# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Manage explicit, redacted memories from the native command line."""

import argparse

from pydantic import TypeAdapter
from rich.console import Console

from datakeel.actions.registry import action_definition
from datakeel.cli.parsers import CommandGroup
from datakeel.core.errors import AuthorizationError
from datakeel.core.memory_models import MemoryCreate, MemoryDeletion, MemoryEntry, MemoryUpdate
from datakeel.memory.service import (
    create_memory,
    delete_memory,
    get_memory,
    list_memories,
    update_memory,
)
from datakeel.storage.database import Database
from datakeel.storage.identity_authorization import effective_scopes

MEMORIES = TypeAdapter(list[MemoryEntry])


def register_parser(commands: CommandGroup) -> None:
    """Expose memory reads and explicit content mutations with actor selection."""
    group = commands.add_parser("memory")
    subcommands = group.add_subparsers(dest="memory_command", required=True)
    for name in ("list", "add", "edit", "delete"):
        command = subcommands.add_parser(name)
        command.add_argument("--actor", default="local")
        command.add_argument("--json", dest="json_output", action="store_true")
        if name in {"edit", "delete"}:
            command.add_argument("memory_id")
        if name in {"add", "edit"}:
            command.add_argument("content")
        if name in {"list", "add"}:
            command.add_argument("--dataset")
        if name == "list":
            command.add_argument("--q")
            command.add_argument("--include-archived", action="store_true")


def _delete(db: Database, memory_id: str, actor: str) -> MemoryDeletion:
    # The existing delete service has no actor argument, so preserve both write and read guards.
    with db.session() as session:
        scope = action_definition("manage_users").auth_scope
        if not {"*", scope}.intersection(effective_scopes(session, actor).scopes):
            msg = f"Memory writes require a server-authorized action scope: {scope}"
            raise AuthorizationError(msg)
    get_memory(db, memory_id, actor=actor)
    return delete_memory(db, memory_id)


def _mutate(db: Database, args: argparse.Namespace) -> MemoryEntry | MemoryDeletion:
    if args.memory_command == "add":
        return create_memory(
            db, MemoryCreate(content=args.content, dataset_id=args.dataset), actor=args.actor
        )
    if args.memory_command == "edit":
        return update_memory(
            db, args.memory_id, MemoryUpdate(content=args.content), actor=args.actor
        )
    return _delete(db, args.memory_id, args.actor)


def _show_entries(console: Console, entries: list[MemoryEntry]) -> None:
    if not entries:
        console.print("No memories found.")
        return
    for entry in entries:
        status = "archived" if entry.archived else "active"
        console.print(
            f"{entry.id}  dataset_id={entry.dataset_id or 'global'}  "
            f"status={status}  strength={entry.current_strength:.2f}\n  {entry.content}"
        )


def dispatch(db: Database, args: argparse.Namespace) -> None:
    """Print complete typed JSON or a readable summary of scoped memory operations."""
    console = Console(soft_wrap=True, markup=False, highlight=False)
    if args.memory_command == "list":
        entries = list_memories(
            db,
            dataset_id=args.dataset,
            query=args.q,
            include_archived=args.include_archived,
            actor=args.actor,
        )
        if args.json_output:
            console.print(MEMORIES.dump_json(entries, indent=2).decode())
        else:
            _show_entries(console, entries)
        return
    result = _mutate(db, args)
    if args.json_output:
        console.print(result.model_dump_json(indent=2))
    elif isinstance(result, MemoryDeletion):
        console.print(f"Deleted memory: {result.memory_id} ({len(result.deleted_ids)} entries)")
    else:
        console.print(f"Memory: {result.id}")
        _show_entries(console, [result])
