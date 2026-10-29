# Training data governance

[中文](LLM_DATA.zh.md) · [Dataset datasheets](DATASHEETS.md) · [Demo tour](DEMO.en.md)

Datakeel checks uploaded JSONL records with local rules and statistics. Analysis is a **dry run**: it saves findings and decisions without changing the source dataset. Creating a cleaned version requires a separate controlled action and human approval. No language model, tokenizer package, remote benchmark or external service is needed.

## Accepted records

Each physical line is parsed independently. A malformed line records its one-based line number and reason; following lines still run. Record IDs bind the source file ID, line number and content hash. Choose automatic format detection or explicitly select `messages`, `instruction` or `preference`.

```jsonl
{"messages":[{"role":"user","content":"Describe a generated harbor scene."},{"role":"assistant","content":"A small boat approaches an empty pier."}]}
{"instruction":"Translate the word boat into Chinese.","input":"","output":"船"}
{"prompt":"Give a concise greeting.","chosen":"Hello!","rejected":"Hello hello hello hello."}
```

Conversation records accept an initial system turn and tool exchanges. Preference `chosen` and `rejected` may also be message arrays. Empty content, invalid roles/order and missing final assistant turns are reported. Content is untrusted data; rules never execute it.

## Import a generated fixture

With your isolated local demo running on port 8773, this standard-library command imports six generated records (including a malformed line) and a separate evaluation file. It prints the new dataset ID. Change the loopback port if your local API uses another one.

```bash
uv run python - <<'PYTHON'
import base64
import json
from urllib.request import Request, urlopen

question = "Why does the fictional silver observatory keep a separate written weather log beside its northern telescope during every evening shift?"
conversation = {"messages": [
    {"role": "user", "content": "Describe a quiet fictional harbor at sunrise."},
    {"role": "assistant", "content": "A small boat rests beside an empty pier while sunlight reaches the water."},
]}
records = [conversation, conversation,
    {"instruction": "Where should the generated report go?", "input": "", "output": "Send it to reviewer@example.test for review."},
    {"prompt": "Choose a greeting.", "chosen": "Welcome to the garden.", "rejected": "Welcome to the garden."},
    {"messages": [{"role": "user", "content": question}, {"role": "assistant", "content": "The independent log helps compare conditions across shifts."}]},
]
source = "\n".join(json.dumps(record) for record in records) + "\n{broken json\n"
def encoded(text):
    return base64.b64encode(text.encode()).decode()
body = {"name": "Generated training governance demo", "files": [
    {"filename": "training.jsonl", "content_base64": encoded(source)},
    {"filename": "evaluation.txt", "content_base64": encoded(question + "\n")},
]}
request = Request("http://127.0.0.1:8773/api/datasets", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
with urlopen(request, timeout=30) as response:
    print(response.read().decode())
PYTHON
```

## Use the dataset page

Open a dataset from **Data library → Dataset → Text data governance**. Select the source version, record format, maximum estimated tokens and contamination n-gram size. Opening the section reads saved reports; **Analyze and preview cleaning** explicitly starts the local scan.

The report shows affected-record counts per rule, parsed and total records, Chinese/English/mixed/uncertain language distribution, confidence, file summaries, duplicate and near-duplicate groups, evaluation hits and preference length bias. Counts for different rules overlap and must not be added to estimate unique affected records. Language percentages use all checked records as their denominator, so malformed records can make the displayed percentages total less than 100%.

Samples show source file/line, stable record ID, redacted preview, decision and reasons. Highlighted evidence and original field offsets identify findings without displaying detected personal values or secrets. Samples and displayed duplicate groups/hits are bounded by `sample_limit`, default 50 (maximum 200). **Download complete decision ledger** exports every keep/drop/redact decision as JSONL, with the ledger SHA-256 beside it. Source objects retain their original access and download behavior; redacted report previews do not alter original uploads.

### Register your own evaluation set

Import your evaluation questions as `.jsonl` or `.txt` files. Under **Register your evaluation set**, name the set, select already imported files in the dataset and register the version-pinned snapshot. Select the registered sets before analyzing. Selected evaluation files from the training dataset are excluded from the training scan. The API also accepts evaluation files from a different existing dataset.

Contamination checks use configurable n-gram overlap (default 13), with normalized containment and conservative fuzzy matching for lightly edited entries. A hit identifies the user-registered evaluation entry. No benchmark questions are bundled. Without a selected evaluation set, an absence of contamination hits means no comparison was performed.

### Approve cleaning

Review the **Cleaning preview**, individual decisions and complete ledger. **Review cleaning plan** prepares a frozen plan for that exact analysis. Inspect source version, affected objects and digest; only **Approve and create a cleaned training version** authorizes execution. Rejecting or allowing the plan to expire changes no dataset. Changing the selected source, report or configuration clears the displayed plan.

The cleaning policy is deterministic:

- Drop malformed/oversized records, invalid conversation structure, empty required fields, over-limit records, unclosed code fences, exact/near duplicates, indistinguishable preference answers and evaluation contamination.
- Redact detected PII/secrets in retained records with typed placeholders such as `[EMAIL]`, `[PHONE]` and `[BANK_CARD]`. A blocking issue takes precedence over redaction.
- Keep other records. Template responses, repetition, garbling, HTML/URL residue, short answers and prompt conflicts remain review signals; they do not by themselves remove a record.

Execution rereads the frozen source and evaluation bytes, reproduces the decisions and verifies hashes before publication. It writes `.clean.jsonl` outputs into a new immutable manifest; the old version remains available. A single dry run cannot publish another version. The lineage event links the source, resulting version and complete decision ledger, retaining counts, reasons and frozen configuration. Duplicate representatives follow the frozen source/record order.

## Signals and configuration

| Check            | Meaning and limits                                                                                                                                                                                                                      |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Structure        | System at the beginning; valid conversational roles, tool exchanges and final assistant turn; empty fields; unclosed code fences; bounded line bytes.                                                                                   |
| Length           | Deterministic character/word-based token estimate, not a model tokenizer or billing count. Default maximum 8192.                                                                                                                        |
| Language         | Script ratios and common words classify Chinese, English, mixed and uncertain with confidence. Short or unusual text may be uncertain.                                                                                                  |
| Quality          | Repeated trigrams, configurable Chinese/English template phrases, control/replacement/garbling patterns, HTML/URLs and unusually short answers. These heuristics require review.                                                        |
| Duplicates       | Normalized hashes for exact repeats; disk-backed locality-sensitive candidate lookup and text similarity for near repeats. The optional Rust hash comparator is reused when installed. No corpus-wide all-pairs scan.                   |
| Prompt conflicts | A shared normalized prompt with different answers is flagged separately from duplicates.                                                                                                                                                |
| PII/secrets      | Email, mainland/international phones, checksum-valid Chinese identity numbers, Luhn-valid bank cards, IPs, recognized key/token patterns and credential-bearing URLs. Invalid checksums are not treated as valid identity/card numbers. |
| Preference pairs | Empty chosen responses; identical/near-identical answers; ratio of chosen responses longer than rejected.                                                                                                                               |

Near-duplicate candidate lookup uses eight MinHash bands, at most eight candidates per band and at most 64 candidates per incoming record. The first retained original record remains the representative; duplicate samples are bounded representative-to-record groups, not an exhaustive transitive clustering. This cap bounds work and memory, and can miss matches in dense or unusual corpora. Similar wording can also have different meaning: review findings before removing records. These rules do not establish semantic answer quality.

Candidate reads use bounded caches: at most 65,536 band keys of at most 64 bytes each, and 16,384 immutable record rows whose combined string length is at most 8,192 characters per row. Larger rows stay on disk. Optional native fingerprint and exact long-text similarity kernels preserve Python results; short-text edit confirmation stays in Python. See [acceleration](RUST_ACCEL.md) for selection, fallback behavior and feature-cache limits.

For large training datasets, install the optional `datakeel-accel` package with `make check-rust` as described in that guide. This is the recommended setup for the 100,000-record, 60-second performance target. Pure Python remains supported with identical results; its measured CPU and wall times are reported separately.

Training-record deduplication belongs to the training-governance analysis/cleaning endpoints and the built-in `text.training_quality` operator. That operator analyzes records inside `.jsonl` and `.ndjson` files and records duplicate findings without deleting source files. The existing `text.dedup` document operator retains its established behavior: exact identity folds case and whitespace, while approximate matching compares word-token sets using the configured inclusive Jaccard threshold. Only retained documents become representatives. The default document pipeline continues to use `text.dedup`; training-record normalization and near-duplicate rules do not replace it.

The shared `text.pii_redact` operator keeps its existing `emails`, `phones` and `replacement` parameter schema. The default literal `replacement="[REDACTED]"` selects the new typed placeholders; any other custom replacement is used verbatim. Email/phone toggles remain effective. Table PII inference and explicit memory writes reuse the same detector and validated number checks. Memory writes preserve the established generic `[REDACTED]` label for retained-context compatibility; training cleaning keeps typed placeholders.

All thresholds and word lists are frozen in each report. The HTTP `config` object accepts `format`, `max_tokens`, `near_distance`, `near_similarity`, `repetition_threshold`, `refusal_phrases`, `contamination_ngram`, `contamination_threshold`, `sample_limit` and `max_line_bytes`. The Web form exposes the commonly changed subset; use HTTP for the remaining fields. Small n-grams or relaxed thresholds can increase false positives; inspect the ledger before cleaning.

## Quality and datasheets

Recorded training evidence participates in the existing five-dimension score. Dimension weights stay unchanged. Completeness, consistency and uniqueness are capped by the corresponding recorded affected-record fractions; annotation and distribution retain their existing behavior. Datasets without recorded training signals, including image-only datasets, preserve their earlier scores.

A datasheet generated for the analyzed version gains measured facts for language distribution, deduplication rate, PII-affected records, contamination rate, format-error rate, record counts and rule version. Ratios and counts retain typed units and pass the existing citation/number validator. Generate a new datasheet after analysis or cleaning; an already saved document is immutable. See [the datasheet reference](DATASHEETS.md).

## HTTP, CLI and Agent

Replace IDs below with uploaded objects in your own local workspace. `DATAKEEL_URL` is the origin where your local API is running.

```bash
DATAKEEL_URL=http://127.0.0.1:8773
curl --fail "$DATAKEEL_URL/api/datasets/DATASET_ID/text-governance/evaluations" \
  -H 'Content-Type: application/json' \
  -d '{"name":"My generated questions","source_dataset_id":"DATASET_ID","version_id":"VERSION_ID","file_ids":["EVALUATION_FILE_ID"]}'
curl --fail "$DATAKEEL_URL/api/datasets/DATASET_ID/text-governance/analyze" \
  -H 'Content-Type: application/json' \
  -d '{"version_id":"VERSION_ID","evaluation_ids":["EVALUATION_ID"],"config":{"format":"auto","max_tokens":8192,"contamination_ngram":13}}'
curl --fail "$DATAKEEL_URL/api/training-governance/RUN_ID/ledger" -o decisions.jsonl
```

Read reports with `GET /api/datasets/{dataset_id}/text-governance?version_id=...` or `GET /api/training-governance/{run_id}`. `POST /api/training-governance/{run_id}/clean` only prepares an `ActionPlan`. Approval and execution use the existing [controlled-action protocol](ACTIONS.md); this endpoint cannot bypass approval.

```bash
uv run datakeel training-quality DATASET_ID --version-id VERSION_ID
```

The CLI and discoverable Agent read tool `get_training_quality` answer what is wrong with a dataset using actual rule observations. They never publish cleaned files. If no saved report exists, the read path can compute local findings without changing dataset versions. A report describes rule evidence; it does not establish that the training data is correct, legally usable or complete.

Credential assignments recognize English labels (including password, passwd, pwd, api_key, secret and token) and Chinese labels (密码、口令、密钥、令牌、访问密钥、访问令牌), with ASCII/full-width colons, equals signs, 是 or 为. Values of at least eight characters require a letter or digit; punctuation-only or empty assignments are ignored. Complete bare ASCII tokens, including password punctuation, are masked before adjacent Chinese prose. Quote values containing whitespace or Unicode text. Typed credential fields use the same labels. Detection is local and never validates a credential against a service.

Credential URLs stop before CJK prose and Chinese punctuation after the userinfo; the complete username/password remains covered even when it contains Unicode or punctuation. Adjacent instructions and quotation marks are retained. Label-like usernames inside a URL are not interpreted as separate credential assignments; credentials after the URL are still checked independently.

The `scheme://userinfo@` prefix is always redacted even if the host is empty or starts with CJK text. CJK host text remains outside the redacted span, using the same boundary as adjacent prose.

Phone candidates require complete digit boundaries. Mainland 11-digit mobile numbers accept +86/0086 and spaces or hyphens; landlines require an area-code separator or paired ASCII/full-width parentheses around a 0xx/0xxx area code followed by a 7–8 digit subscriber number. Parenthesized North American area codes accept seven-digit subscriber numbers, including 3-4 grouping. Spaces or hyphens may follow the closing parenthesis. Explicit + international numbers retain the existing 8–15 digit bounds. Other long bare numbers, dates, decimal amounts, versions, postal codes and percentages are not inferred to be phones.

Existing typed redaction placeholders are not reported again. Nested surrounding brackets are retained regardless of their ordering. Overlapping findings cover their complete combined span, so a credential URL crossing a labelled password cannot leave either credential partly visible.
