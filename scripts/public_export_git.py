# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run isolated local Git rewrites using a temporary maintenance tool."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import TYPE_CHECKING

from scripts.public_export_models import ExportError, MessageRewrite

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.public_export_models import ExportPolicy

PUBLIC_NAME = "chaw1"
PUBLIC_EMAIL = "34927473+chaw1@users.noreply.github.com"


def run_command(directory: Path, arguments: tuple[str, ...], *, stdin: str | None = None) -> str:
    """Run fixed argv without inherited Git overrides, hooks, signing, or remote prompts."""
    executable = shutil.which(arguments[0])
    if executable is None:
        msg = f"Required maintenance command is unavailable: {arguments[0]}"
        raise ExportError(msg)
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1",
    )
    result = subprocess.run(  # noqa: S603  # Fixed argv, local paths, no shell, isolated Git environment.
        (executable, *arguments[1:]),
        cwd=directory,
        env=environment,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if result.returncode:
        msg = f"{arguments[0]} failed ({result.returncode}): {result.stderr[-4000:].strip()}"
        raise ExportError(msg)
    return result.stdout.strip()


def git(directory: Path, *arguments: str, stdin: str | None = None) -> str:
    """Run Git against an explicitly selected local repository."""
    return run_command(directory, ("git", *arguments), stdin=stdin)


def clone_selected(source: Path, destination: Path, commit: str) -> None:
    """Clone into new storage and retain only the selected revision's reachable history."""
    git(
        destination.parent,
        "clone",
        "--no-local",
        "--no-hardlinks",
        "--no-checkout",
        "--no-tags",
        "--",
        str(source),
        str(destination),
    )
    git(destination, "fetch", "--no-tags", "--no-write-fetch-head", str(source), commit)
    git(destination, "remote", "remove", "origin")
    for ref in git(destination, "for-each-ref", "--format=%(refname)").splitlines():
        git(destination, "update-ref", "-d", ref)
    git(destination, "update-ref", "refs/heads/main", commit)
    git(destination, "symbolic-ref", "HEAD", "refs/heads/main")
    git(destination, "reset", "--hard", commit)
    git(destination, "config", "user.name", PUBLIC_NAME)
    git(destination, "config", "user.email", PUBLIC_EMAIL)
    git(destination, "config", "commit.gpgsign", "false")


def filter_history(repository: Path, policy: ExportPolicy, temporary: Path) -> None:
    """Apply path removal, content replacement, identity normalization, and message rewrites."""
    replacement_path = temporary / "replacements.txt"
    replacement_path.write_text(policy.replacements)
    callback = temporary / "rewrite.py"
    callback.write_text(
        f"commit.author_name = commit.committer_name = {PUBLIC_NAME.encode()!r}\n"
        f"commit.author_email = commit.committer_email = {PUBLIC_EMAIL.encode()!r}\n"
        f"messages = {policy.messages!r}\n"
        "message = messages.get(commit.original_id.decode('ascii'))\n"
        "if message is not None:\n"
        "    commit.message = (message.rstrip() + '\\n').encode('utf-8')\n"
    )
    arguments = [
        "uvx",
        "--from",
        "git-filter-repo",
        "git-filter-repo",
        "--force",
        "--invert-paths",
        "--replace-text",
        str(replacement_path),
        "--commit-callback",
        str(callback),
        "--prune-empty",
        "auto",
        "--prune-degenerate",
        "auto",
        "--replace-refs",
        "delete-no-add",
    ]
    for pattern in policy.excluded_patterns:
        option = "--path-glob" if any(char in pattern for char in "*?[") else "--path"
        arguments.extend((option, pattern))
    run_command(repository, tuple(arguments))


def message_rewrites(repository: Path, policy: ExportPolicy) -> tuple[MessageRewrite, ...]:
    """Join original message mappings to the maintenance tool's complete commit map."""
    mapping = repository / ".git" / "filter-repo" / "commit-map"
    rewritten: list[MessageRewrite] = []
    for line in mapping.read_text().splitlines()[1:]:
        original, filtered = line.split()
        if original in policy.messages:
            rewritten.append(
                MessageRewrite(
                    original_commit=original,
                    filtered_commit=filtered if set(filtered) != {"0"} else None,
                    message=policy.messages[original].rstrip(),
                )
            )
    return tuple(sorted(rewritten, key=lambda item: item.original_commit))


def collapse_snapshot(repository: Path) -> None:
    """Create one normalized commit and remove all unreachable rewritten history."""
    if git(repository, "rev-list", "--all"):
        tree = git(repository, "rev-parse", "HEAD^{tree}")
    else:
        tree = git(repository, "mktree", stdin="")
    commit = git(repository, "commit-tree", tree, "-m", "chore: 导出公开快照")
    git(repository, "update-ref", "refs/heads/main", commit)
    git(repository, "reset", "--hard", commit)
    git(repository, "reflog", "expire", "--expire=now", "--all")
    git(repository, "gc", "--prune=now")
