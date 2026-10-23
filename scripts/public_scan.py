# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Scan public history and worktrees without exposing matched values or following symlinks."""

from __future__ import annotations

import os
import re
import stat
import subprocess
from typing import TYPE_CHECKING

from scripts.public_scan_models import BlobScan, LineFinding, ScanFinding, ScanReport
from scripts.public_scan_rules import excluded_path, noreply_email, text_findings

if TYPE_CHECKING:
    from pathlib import Path

MAX_BLOB_BYTES = 5 * 1024 * 1024
_IMAGE_MAGIC = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"II*\0",
    b"MM\0*",
    b"\0\0\x01\0",
)
_BINARY_MAGIC = (
    *_IMAGE_MAGIC,
    b"wOF2",
    b"wOFF",
    b"OTTO",
    b"\0\x01\0\0",
    b"PK\x03\x04",
    b"\x1f\x8b",
    b"%PDF-",
)


def _git(repo: Path, *arguments: str) -> bytes:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return subprocess.run(  # noqa: S603  # Fixed Git executable and argument arrays; no shell.
        ["git", "-C", str(repo), *arguments],  # noqa: S607  # Git is the required maintainer tool.
        check=True,
        capture_output=True,
        env=environment,
        timeout=60,
    ).stdout


def _image(data: bytes) -> bool:
    return (
        data.startswith(_IMAGE_MAGIC)
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
        or (data[4:8] == b"ftyp" and data[8:12] in {b"avif", b"avis", b"heic", b"heif"})
        or bool(re.match(rb"\s*(?:<\?xml[^>]*>\s*)?<svg(?:\s|>)", data[:1024]))
    )


def _text(data: bytes) -> str | None:
    if data.startswith(_BINARY_MAGIC) or (data.startswith(b"RIFF") and data[8:12] == b"WEBP"):
        return None
    encodings = (
        (b"\xff\xfe\0\0", "utf-32"),
        (b"\0\0\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    )
    encoding = next(
        (name for signature, name in encodings if data.startswith(signature)), "utf-8-sig"
    )
    try:
        text = data.decode(encoding)
    except UnicodeError:
        text = data.decode("latin-1")
    return None if "\0" in text else text


def _scan_blob(path: str, data: bytes, patterns: tuple[str, ...]) -> BlobScan:
    findings: list[LineFinding] = []
    if len(data) > MAX_BLOB_BYTES:
        findings.append(LineFinding(line=1, rule="oversized_blob"))
    text = _text(data)
    if text is not None:
        findings.extend(text_findings(path, text, patterns))
    return BlobScan(findings=tuple(findings), image=_image(data))


def _located(commit: str, path: str, findings: tuple[LineFinding, ...]) -> list[ScanFinding]:
    return [
        ScanFinding(commit=commit, path=path, line=item.line, rule=item.rule) for item in findings
    ]


def _metadata(repo: Path, commit: str, patterns: tuple[str, ...]) -> list[ScanFinding]:
    fields = (
        _git(repo, "show", "-s", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", commit)
        .decode("utf-8", errors="replace")
        .split("\0", 4)
    )
    findings = _located(
        commit, "<commit-message>", text_findings("", fields[4], patterns, message=True)
    )
    for index, path in ((0, "<author>"), (2, "<committer>")):
        findings.extend(_located(commit, path, text_findings("", fields[index], patterns)))
        if not noreply_email(fields[index + 1]):
            findings.append(ScanFinding(commit=commit, path=path, line=1, rule="email"))
    return findings


def _tree(repo: Path, commit: str) -> tuple[tuple[str, str, str], ...]:
    entries: list[tuple[str, str, str]] = []
    for entry in _git(repo, "ls-tree", "-r", "-z", commit).split(b"\0"):
        if not entry:
            continue
        metadata, path = entry.split(b"\t", 1)
        _mode, kind, oid = metadata.decode("ascii").split()
        entries.append((path.decode("utf-8", errors="surrogateescape"), kind, oid))
    return tuple(entries)


def scan_repository(repo: Path, excluded_patterns: tuple[str, ...]) -> ScanReport:
    """Scan all reachable history, caching blobs while retaining every commit/path occurrence."""
    commits = (
        _git(repo, "rev-list", "--topo-order", "--reverse", "--all").decode("ascii").splitlines()
    )
    cache: dict[tuple[str, str], BlobScan] = {}
    images: set[str] = set()
    findings: list[ScanFinding] = []
    for commit in commits:
        findings.extend(_metadata(repo, commit, excluded_patterns))
        for path, kind, oid in _tree(repo, commit):
            findings.extend(_located(commit, path, text_findings("", path, excluded_patterns)))
            if excluded_path(path, excluded_patterns):
                findings.append(ScanFinding(commit=commit, path=path, line=1, rule="excluded_path"))
            if kind != "blob":
                findings.append(
                    ScanFinding(commit=commit, path=path, line=1, rule="unsupported_entry")
                )
                continue
            name = path.rsplit("/", 1)[-1]
            context = (
                name
                if name in {"package-lock.json", "uv.lock"}
                else ".py"
                if name.endswith(".py")
                else ""
            )
            key = (oid, context)
            if key not in cache:
                cache[key] = _scan_blob(
                    path, _git(repo, "cat-file", "blob", oid), excluded_patterns
                )
            result = cache[key]
            findings.extend(_located(commit, path, result.findings))
            if result.image:
                images.add(path)
    unique = {(item.commit, item.path, item.line, item.rule): item for item in findings}
    return ScanReport(
        findings=tuple(unique.values()),
        images=tuple(sorted(images)),
        scanned_commits=len(commits),
        scanned_blobs=len({oid for oid, _ in cache}),
    )


def _worktree_blob(repo: Path, path: str) -> bytes | None:
    target = repo / path
    if any(
        parent.is_symlink()
        for parent in target.parents
        if parent != repo and parent.is_relative_to(repo)
    ):
        msg = "A worktree entry cannot traverse a symlink"
        raise ValueError(msg)
    try:
        mode = target.lstat().st_mode
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(mode):
        return os.fsencode(target.readlink())
    if not stat.S_ISREG(mode):
        msg = "Unsupported worktree entry"
        raise ValueError(msg)
    return target.read_bytes()


def scan_worktree(repo: Path) -> ScanReport:
    """Scan current tracked and untracked nonignored files, including unstaged edits."""
    repo = repo.resolve()
    paths = sorted(
        {
            path.decode("utf-8", errors="surrogateescape")
            for path in _git(
                repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard"
            ).split(b"\0")
            if path
        }
    )
    findings: list[ScanFinding] = []
    images: list[str] = []
    scanned = 0
    for path in paths:
        try:
            data = _worktree_blob(repo, path)
        except (OSError, ValueError):
            findings.append(
                ScanFinding(commit="<worktree>", path=path, line=1, rule="unsupported_entry")
            )
            continue
        if data is None:
            continue
        findings.extend(_located("<worktree>", path, text_findings("", path, ())))
        scanned += 1
        result = _scan_blob(path, data, ())
        findings.extend(_located("<worktree>", path, result.findings))
        if result.image:
            images.append(path)
    return ScanReport(
        findings=tuple(findings),
        images=tuple(images),
        scanned_commits=0,
        scanned_blobs=scanned,
    )
