# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Rewrite relative README links and images to absolute GitHub URLs for PyPI wheels."""

from __future__ import annotations

import base64
import hashlib
import re
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_FENCE_SPLIT_RE = re.compile(r"(```.*?```)", re.DOTALL)
_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")
_HTML_IMG_SRC_RE = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)
_HTML_A_HREF_RE = re.compile(r'(<a\b[^>]*?\bhref=")([^"]+)(")', re.IGNORECASE)
_ABSOLUTE_PREFIXES = ("http://", "https://", "mailto:", "data:", "#")


def _github_slug(repo_url: str) -> str:
    cleaned = repo_url.removesuffix(".git").rstrip("/")
    prefix = "https://github.com/"
    if not cleaned.startswith(prefix):
        msg = f"Expected a GitHub repository URL, got: {repo_url}"
        raise ValueError(msg)
    return cleaned.removeprefix(prefix)


def _rewrite_prose(text: str, *, raw_base: str, blob_base: str) -> str:
    def _raw_url(target: str) -> str:
        return (
            target if target.startswith(_ABSOLUTE_PREFIXES) else f"{raw_base}{target.lstrip('./')}"
        )

    def _blob_url(target: str) -> str:
        if target.startswith(_ABSOLUTE_PREFIXES):
            return target
        return f"{blob_base}{target.lstrip('./')}"

    updated = _MD_IMAGE_RE.sub(lambda m: f"![{m.group(1)}]({_raw_url(m.group(2))})", text)
    updated = _HTML_IMG_SRC_RE.sub(
        lambda m: f"{m.group(1)}{_raw_url(m.group(2))}{m.group(3)}", updated
    )
    updated = _MD_LINK_RE.sub(lambda m: f"[{m.group(1)}]({_blob_url(m.group(2))})", updated)
    return _HTML_A_HREF_RE.sub(
        lambda m: f"{m.group(1)}{_blob_url(m.group(2))}{m.group(3)}", updated
    )


def rewrite_readme_urls(
    markdown: str,
    *,
    repo_url: str = "https://github.com/chaw1/datakeel",
    ref: str = "main",
) -> str:
    """Convert relative README image and link paths to absolute GitHub URLs outside code fences."""
    slug = _github_slug(repo_url)
    raw_base = f"https://raw.githubusercontent.com/{slug}/{ref}/"
    blob_base = f"https://github.com/{slug}/blob/{ref}/"
    parts = _FENCE_SPLIT_RE.split(markdown)
    return "".join(
        part if index % 2 == 1 else _rewrite_prose(part, raw_base=raw_base, blob_base=blob_base)
        for index, part in enumerate(parts)
    )


def relative_image_urls(markdown: str) -> tuple[str, ...]:
    """Return any relative image URLs outside fenced code blocks."""
    found: list[str] = []
    for index, part in enumerate(_FENCE_SPLIT_RE.split(markdown)):
        if index % 2 == 1:
            continue
        found.extend(
            match.group(2)
            for match in _MD_IMAGE_RE.finditer(part)
            if not match.group(2).startswith(_ABSOLUTE_PREFIXES)
        )
        found.extend(
            match.group(2)
            for match in _HTML_IMG_SRC_RE.finditer(part)
            if not match.group(2).startswith(_ABSOLUTE_PREFIXES)
        )
    return tuple(found)


def _record_digest(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest},{len(data)}"


def _rewrite_metadata_bytes(raw: bytes, *, repo_url: str, ref: str) -> bytes:
    text = raw.decode("utf-8")
    separator = "\r\n\r\n" if "\r\n\r\n" in text else "\n\n"
    if separator not in text:
        return raw
    headers, body = text.split(separator, 1)
    rewritten = rewrite_readme_urls(body, repo_url=repo_url, ref=ref)
    return f"{headers}{separator}{rewritten}".encode()


def _update_record_bytes(raw: bytes, target_name: str, updated_data: bytes) -> bytes:
    replacement = f"{target_name},{_record_digest(updated_data)}"
    lines = [
        replacement if line.startswith(f"{target_name},") else line
        for line in raw.decode("utf-8").splitlines()
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def rewrite_wheel_metadata(
    wheel_path: Path,
    *,
    repo_url: str = "https://github.com/chaw1/datakeel",
    ref: str = "main",
) -> None:
    """Rewrite relative README URLs inside a wheel's METADATA and update its RECORD hash."""
    with zipfile.ZipFile(wheel_path, "r") as reader:
        entries = [(info, reader.read(info)) for info in reader.infolist()]

    meta_name = next(
        (i.filename for i, _ in entries if i.filename.endswith(".dist-info/METADATA")), None
    )
    record_name = next(
        (i.filename for i, _ in entries if i.filename.endswith(".dist-info/RECORD")), None
    )
    if meta_name is None:
        return

    updated_meta = next(
        _rewrite_metadata_bytes(data, repo_url=repo_url, ref=ref)
        for info, data in entries
        if info.filename == meta_name
    )

    temp_path = wheel_path.with_suffix(".whl.tmp")
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as writer:
        for info, data in entries:
            if info.filename == meta_name:
                writer.writestr(info, updated_meta)
            elif info.filename == record_name:
                writer.writestr(info, _update_record_bytes(data, meta_name, updated_meta))
            else:
                writer.writestr(info, data)
    temp_path.replace(wheel_path)
