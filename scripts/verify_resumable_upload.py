# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Verify a real loopback HTTP resume with generated sparse data below five GiB.

Run an isolated local API, then execute:
    uv run python scripts/verify_resumable_upload.py --url http://127.0.0.1:8816

The initial client closes after half the chunks. A fresh client asks for missing
ordinals, sends only those chunks in reverse order and verifies downloaded bytes.
"""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from rich.console import Console

from datakeel.core.uploads import UploadView
from datakeel.storage.objects import digest

_MAX_BYTES = 5 * 1024**3


def _request(client: httpx.Client, method: str, path: str) -> UploadView:
    response = client.request(method, path)
    response.raise_for_status()
    return UploadView.model_validate(response.json())


def _send(client: httpx.Client, prefix: str, source: Path, upload: UploadView) -> int:
    with source.open("rb") as stream:
        for ordinal in reversed(upload.missing_chunks):
            stream.seek(ordinal * upload.chunk_bytes)
            response = client.put(
                f"{prefix}/chunks/{ordinal}",
                content=stream.read(upload.chunk_bytes),
                headers={"Content-Type": "application/octet-stream"},
            )
            response.raise_for_status()
    return len(upload.missing_chunks)


def _generate(path: Path, size: int, chunk_bytes: int) -> None:
    with path.open("wb") as stream:
        stream.truncate(size)
        for ordinal in range((size + chunk_bytes - 1) // chunk_bytes):
            stream.seek(ordinal * chunk_bytes)
            marker = f"generated-chunk-{ordinal}".encode()
            stream.write(marker[: min(len(marker), size - stream.tell())])


def _verify_download(client: httpx.Client, dataset_id: str, checksum: str) -> str:
    files = client.get(f"/api/datasets/{dataset_id}/files")
    files.raise_for_status()
    identifier = str(files.json()[0]["id"])
    digest_value = hashlib.sha256()
    with client.stream(
        "GET", f"/api/datasets/{dataset_id}/files/{identifier}/download"
    ) as response:
        response.raise_for_status()
        for part in response.iter_bytes():
            digest_value.update(part)
    actual = digest_value.hexdigest()
    if actual != checksum:
        message = "Downloaded actual object does not match the generated source SHA-256"
        raise ValueError(message)
    return actual


def run(url: str, source: Path, chunk_bytes: int) -> dict[str, str | int | float]:
    """Close the initial connection and resume through an independent client."""
    started = perf_counter()
    checksum = digest(source)
    with httpx.Client(base_url=url, trust_env=False, timeout=120) as client:
        response = client.post(
            "/api/uploads",
            json={
                "idempotency_key": f"generated-resume-{uuid4().hex}",
                "name": "Generated resumability verification",
                "filename": source.name,
                "total_bytes": source.stat().st_size,
                "sha256": checksum,
                "chunk_bytes": chunk_bytes,
            },
        )
        response.raise_for_status()
        upload = UploadView.model_validate(response.json())
        prefix = f"/api/uploads/{upload.id}"
        initial = upload.model_copy(update={"missing_chunks": upload.missing_chunks[::2]})
        first_count = _send(client, prefix, source, initial)
    with httpx.Client(base_url=url, trust_env=False, timeout=120) as resumed:
        progress = _request(resumed, "GET", prefix)
        if set(progress.missing_chunks) & set(initial.missing_chunks):
            message = "Resume requested chunks that were already acknowledged"
            raise ValueError(message)
        resumed_count = _send(resumed, prefix, source, progress)
        complete = _request(resumed, "POST", f"{prefix}/complete")
        actual = _verify_download(resumed, complete.dataset_id or "", checksum)
    return {
        "upload_id": upload.id,
        "dataset_id": complete.dataset_id or "",
        "total_bytes": upload.total_bytes,
        "chunk_bytes": chunk_bytes,
        "chunk_count": upload.chunk_count,
        "initial_chunks": first_count,
        "resumed_chunks": resumed_count,
        "resent_acknowledged_chunks": 0,
        "source_sha256": checksum,
        "download_sha256": actual,
        "elapsed_seconds": round(perf_counter() - started, 3),
    }


def main() -> None:
    """Generate local sparse data and emit a machine-readable real-upload receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8816")
    parser.add_argument("--bytes", type=int, default=128 * 1024**2 + 123, dest="size")
    parser.add_argument("--chunk-bytes", type=int, default=4 * 1024**2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    url = str(args.url)
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only an explicitly selected loopback HTTP API is supported")
    if not 0 < args.size < _MAX_BYTES or args.chunk_bytes <= 0:
        parser.error("Choose positive data smaller than 5 GiB and a positive chunk size")
    with tempfile.TemporaryDirectory(prefix="datakeel-generated-upload-") as directory:
        source = Path(directory) / "generated.bin"
        _generate(source, args.size, args.chunk_bytes)
        result = json.dumps(run(url, source, args.chunk_bytes), indent=2)
    if args.output:
        args.output.write_text(result + "\n")
    Console().print(result, soft_wrap=True, markup=False)


if __name__ == "__main__":
    main()
