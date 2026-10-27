# Dataset comparison and delivery

[中文](RELEASES.zh.md) · [Guided tour](DEMO.en.md)

Open a dataset in **Data library → Versions**. Select two versions from this dataset, then click **Compare versions**. The five categories are added, removed, content changed (SHA-256 changed), metadata only, and unchanged. Each category has a whole-comparison count and bounded file pages. Annotation counts, label counts, mean file quality and evidence decision counts appear beside the file differences. Missing quality values are represented by the version summary's recorded measurement rules.

Legacy versions preserve file manifests without historical governance snapshots. Comparison quality scores use the dataset's current quality configuration; evidence decision summaries use the current active decisions associated with each version.

The equivalent local command is:

```bash
uv run datakeel version-diff DATASET_ID BEFORE_VERSION AFTER_VERSION --limit 50 --category content_changed --json
```

`--offset` selects another page; omitting `--category` returns a mixed page. The API is `GET /api/datasets/{dataset}/diff?before={version}&after={version}&offset=0&limit=50`. Versions from different datasets are rejected. Files align by their manifest file ID: shared IDs compare SHA-256 and then metadata; a derived artifact with a new ID is a new file.

## Publish and inspect

In **Versions → Publish a release**, select a source version, enter a semantic tag such as `v1.2.0` and release notes, then click **Review release plan**. Inspect the frozen parameters, file impact, digest and irreversible status. **Approve and publish release** signs and executes this exact plan. Preparing a plan does not publish anything. The same pending plan is also available in **Approvals**.

The resulting release appears in the list. Expand its tag to see the source version, manifest SHA-256, notes, total bytes and paginated frozen files. Publication freezes the current governance metadata, quality measurements and evidence decision summary captured when its release plan was prepared. Release files, metadata and hashes are immutable. Subsequent changes require another version and another release; the existing version-generation workflow is unchanged.

For automation, use the existing controlled-action protocol with `POST /api/actions/publish_release/prepare` and parameters `dataset_id`, `version_id`, `tag`, `notes`; sign the returned plan at `POST /api/approvals/{plan_id}` and execute it at `POST /api/actions/{plan_id}/execute`. Approval and execution must carry the returned digest, and execution uses the plan's operation ID. Read releases with `GET /api/datasets/{dataset}/releases`, `GET /api/releases/{release}` and `GET /api/releases/{release}/files?offset=0&limit=50`.

## Export and verify independently

Click **Export delivery package** in the release detail to download a gzip tar archive. The equivalent command writes an archive or a new directory:

```bash
uv run datakeel release-export RELEASE_ID --output delivery.tar.gz
uv run datakeel release-export RELEASE_ID --output delivery-directory
```

The HTTP equivalent is `POST /api/releases/{release_id}/export`, which returns the tar archive with media type `application/gzip`. Archives are reproducible: members are sorted by path, owner and group names are empty, uid/gid are 0, permissions are `0644`, modification times are 0, and the gzip header carries no file name or timestamp. Repeated exports of one release are byte-identical and never reveal the server's system account names.

The package contains:

- `MANIFEST.json`: expected relative paths, byte counts, SHA-256, media types, source versions, lineage references, annotation and label counts, metadata and required metadata fields, plus a canonical manifest hash.
- `RECORDS.json`: the independently checked receipt-side dataset metadata, plus metadata, annotation and label totals, and lineage for each payload.
- `files/`: the actual file content.

Keep both JSON files with the payload. Paths are relative; credentials and internal physical storage paths are excluded. Metadata is filtered by field role and value structure: fields declared as locations (`path`, fields ending in `path` such as `source_path`, `object_key`, `storage_uri`), credential fields, storage URIs such as `file://` or `s3://`, and URLs carrying credentials are removed. Every other value is kept as is, so labels that start with `/` (for example `/m/01yrx`) remain and are counted. The manifest schema is [contracts/delivery-manifest.schema.json](../contracts/delivery-manifest.schema.json) and export validates it. The manifest hash detects a changed manifest; it is an integrity checksum, not a digital signature proving a sender's identity. Keep a trusted copy of that hash when authenticity matters.

Payload paths contain an ordinal directory and a percent-encoded basename; long encoded names are shortened with a digest suffix. Follow the exact paths in `MANIFEST.json`; do not decode or rename them before verification. The source release snapshot hash shown in the Web and the delivery manifest's canonical hash cover different serializations and are not interchangeable. The delivery checksum hashes UTF-8 JSON with sorted object keys, compact separators and unescaped Unicode, excluding only the top-level `manifest_sha256` field. Export includes schema defaults; verification hashes the fields actually received, so removing a default-valued field is detected. Use the hash from the expected delivery manifest when comparing delivery manifests.

The recipient can run reconciliation with an installed Datakeel command, without an API, database, object store or model service:

```bash
datakeel reconcile delivery.tar.gz --manifest MANIFEST.json
datakeel reconcile delivery-directory --manifest MANIFEST.json --json
```

The default manifest path is resolved inside the delivery. Human output includes Chinese and English; `--json` emits a structured report. Exit status is `0` only when all six categories pass, `1` on a mismatch, and `2` when the delivery or manifest cannot be read or validated. An invalid input with `--json` returns `error: "invalid_delivery"` and an error-class `reason`, without echoing its contents. Checks cover file count; total and per-file byte sizes; SHA-256; annotation and label counts; required metadata fields and values; and valid lineage references to registered source versions. Metadata and annotation checks compare `RECORDS.json` with `MANIFEST.json`; they do not infer annotation semantics from arbitrary media bytes. Missing receipt records fail rather than silently passing.

For annotation statistics, an explicit nonnegative integer `annotation_count` or `label_count` in metadata takes precedence. Otherwise the registered plural collection (`annotations` or `labels`), then singular collection (`annotation` or `label`), supplies its list length; a present nonempty scalar or object counts as one, and no registered value counts as zero. Receipt-side collection-derived statistics are checked against the declared counts when those fields are present. An explicit count remains authoritative even if a collection is also present; a changed collection is independently caught by metadata comparison.

Metadata checks compare dataset and file fields, required-field presence and complete JSON values. Object-key ordering does not matter; array order and scalar representations do. For example, `true`, `1`, `1.0` and `"1"` are distinct. Required fields may contain JSON `null` when the expected value is also `null`; this check does not impose a separate non-null business rule.

To demonstrate corruption, extract a copy of the package, change one payload byte and run the same command:

```bash
mkdir received
tar -xzf delivery.tar.gz -C received
python3 - <<'PY'
import json
from pathlib import Path

root = Path("received")
manifest = json.loads((root / "MANIFEST.json").read_text())
payload = root / manifest["files"][0]["path"]
with payload.open("r+b") as stream:
    first = stream.read(1)
    stream.seek(0)
    stream.write(bytes([first[0] ^ 1]) if first else b"x")
PY
datakeel reconcile received --manifest MANIFEST.json
```

The hash category names the altered file and its expected and actual values. A nonempty file changed in place keeps its size, so the byte category still passes. For metadata, annotation or lineage exercises, change the corresponding record in `RECORDS.json` and retain the expected manifest.

## Archive a platform-side check

In release details, click **Reconcile stored objects**. The platform reads actual stored objects and archives the same six categories and differences. Reloading keeps the history. API equivalents are `POST /api/releases/{release}/reconcile` and `GET /api/releases/{release}/reconciliations`; the local command is:

```bash
uv run datakeel release-reconcile RELEASE_ID --json
```

## Resume a chunked upload

`POST /api/uploads` accepts `idempotency_key`, `name`, `filename`, `total_bytes`, the complete source `sha256`, `chunk_bytes` and optional `metadata`. Keep the returned upload ID. `GET /api/uploads/{id}` returns `received_chunks` and `missing_chunks`, so a new client can send only missing zero-based chunks. Upload each exact-sized chunk using `PUT /api/uploads/{id}/chunks/{ordinal}` with `Content-Type: application/octet-stream` and raw bytes. Submit `POST /api/uploads/{id}/complete` without a body to verify and import the file. The receipt then contains state `COMPLETE` and `dataset_id`.

Identical chunk retries merge; a conflicting duplicate is rejected. Chunks may arrive out of order. Overlapping writes to the same upload are rejected with `409`; the client can retry after the first write finishes. The same initialization idempotency key resumes the same declaration, and changing that declaration returns `409`. Independent keys represent independent imports. Completion retries return the existing result. The whole source SHA-256 is checked before import, and the actual persisted object is read and hashed again before the dataset transaction commits. Invalid lengths, missing chunks or a mismatched hash return `422` without creating the dataset; unknown upload IDs return `404`.

Configuration bounds are `DATAKEEL_UPLOAD_MAX_CHUNK_BYTES` (default 8 MiB, maximum 64 MiB), `DATAKEEL_UPLOAD_MAX_CONCURRENCY` (default 4, maximum 32), and `DATAKEEL_UPLOAD_MAX_FILE_BYTES` (default 5 GiB, maximum 1 TiB). An upload may contain at most 100,000 chunks; choose a chunk size consistent with that bound. Exceeding the concurrent-writer limit returns `409`.

Upload chunks are staged under `uploads/<upload ID>/` in the configured `DATAKEEL_HOME`. After a successful completion commits the dataset, the staged chunks are deleted; if the process stops between that commit and the deletion, calling completion again finishes the cleanup. Unfinished uploads, and uploads whose completion failed because of missing chunks, wrong sizes or a hash mismatch, keep their chunks so they can be resumed or inspected. This release has no abort endpoint and no automatic expiry; an operator removes that directory when it is no longer needed. Plan disk capacity for chunks of unfinished uploads and the temporary full-file assembly. Resume survives a client or process restart on the same persistent filesystem. Multiple API hosts must use the same staging volume and database, or route an upload consistently to its original host; sharing only PostgreSQL does not share chunk bytes. Process locks protect overlapping writers but do not replicate staging files.

The release browser walkthrough can be replayed with `npm --prefix web run smoke:release -- http://127.0.0.1:8816 OUTPUT_DIRECTORY`. It creates generated fixtures, compares two versions, approves publication through the UI, downloads and verifies a package, changes one payload byte, and checks that an archived platform report survives reloading. The chosen output directory receives screenshots and machine-readable results. It permits only requests to the given loopback origin and requires zero browser errors.
