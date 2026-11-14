# Offline Evaluation, Mutation Testing & Quality Gates

[中文](VERIFICATION.zh.md) · [Documentation Hub](README.md) · [Code Standards](CODE_STANDARDS.md) · [Test Speed & CI Shards](TEST_SPEED.md) · [Back to README](../README.md)

Datakeel ships deterministic offline evaluation suites, a mutation-testing harness, screenshot/UI smoke checks, and a unified `make check` repository gate.

## Offline evaluation commands

```bash
uv run datakeel eval --provider fake
uv run datakeel eval --provider fake --json
uv run datakeel eval-evidence
uv run datakeel eval-evidence --json
uv run datakeel eval-ask
uv run datakeel eval-ask --json
uv run datakeel eval-kg --json
uv run datakeel eval-kg --profile replay-flash --json
uv run datakeel eval-kg --suite image --json
uv run datakeel eval-route
uv run python scripts/mutate.py --output mutation-results.json
```

## Golden Agent evaluation (`eval`)

The **58 golden cases** execute real local services against isolated generated fixtures with scripted model replies (zero external model calls or charges unless `--provider openai` or `--provider anthropic` is explicitly opted into):

- **Core (12)**: reads, actions, approvals, loop guards, token/USD budgets, cross-turn references and dry-run mode.
- **Evidence (4)**: queries, unknown-state explanations, selected-version creation and deletion approval.
- **Enterprise Ask (4)**: answered query, clarification, refusal and answer changed by a controlled metric update.
- **Advanced Agent (12)**: delegation, canary leak guard, prompt-injection approval stop and cross-conversation memory.
- **Knowledge Graph (4)**: queries, missing-endpoint explanations, replay and external approval with zero conversation executions.
- **Knowledge Questions & Images (7)**: 4 knowledge-question cases (candidate labels, missing catalog assets, subject ambiguity, rejected claims) + 3 image transcription evidence-boundary cases.
- **Governance, Quality, Standards, Assets & Training (8)**: 1 ungranted data-asset refusal, 2 standards compliance/usage cases, 2 table quality rule/issue cases, 1 annotation agreement/acceptance case, 2 training distribution/leakage cases, and 1 LLM training-data check.
- **One-Sentence Planning (6)**: multi-step chain with no writes before confirmation, missing-project follow-up, missing-permission refusal, permission checked before question, unknown parameter asked rather than dropped, and unsupported request explanation.

Repeating `eval` reports the previous run ID alongside deltas in passed cases, tokens and cost; `--json` emits the full report and any failed case returns a nonzero exit status.

## Mutation testing (`scripts/mutate.py`)

`scripts/mutate.py` requires all **856 mutations** in temporary source copies to finish as `KILLED`:

- **Core, Evidence, Ask & Runtime**: `unknown → absent` assertion bypass caught by `explain_sample` golden check; near-duplicate Hamming threshold `+4` killed by an `A–B (6) / B–C (6) / A–C (12)` image chain; candidate-ID SQL boundary and numeric guessing on `unanswerable`; signed resume authorization and tool-call idempotency.
- **Workflows, Routing, Agent, KG, Assets & Standards**: signed workflow resume, intent score margin, cycle detection, failed-attempt budget settlement; canary, delegation depth, tool scope, memory hard-delete and per-question reinforcement guards; endpoint verification, pending-review discard, cache model identity; candidate review labels, whole-identifier splitting, unsupported knowledge routing, post-rejection relationship cleanup; missing-grant, expiry, revocation, exact-scope, tool-cache replay, source-manifest, message replay, version-producer checks; compliance ranking inversion and confirmed-mapping discard.
- **v0.13.0–v0.14.0**: time-series detection, releases and delivery, custom operators, image routing and coordinates, data assets, metric drafts, quality rules, metadata import, annotation quality, datasheets, scale benchmark, chart selection, follow-up resolution and MCP refusal of `approve_plan` / `execute_plan`.
- **v0.15.0**: training splits, exports, leakage and write authorization, LLM training-data checks, redaction, deduplication and cleaning, production roles, assignments, revisions, prediction imports and the annotation workbench.
- **v0.16.0–v0.17.0**: team-tier lease expiry and deadline boundary, exactly-once reaping rereading renewals, review separation in claims and review queue, skill filter, whole-package returns, PostgreSQL lock order, per-person load serialization; template attribute checks, reclaim/dispatch freeze scope, effective lease deadline, filename search before paging, path sanitization, current load dispatch preview, running-stage leases, and hiding a reviewer's own work.
- **v0.18.0**: privacy credential heuristics (`secret`, `token`, `key`, `auth`, character classes, digits, internal capitals, 8-char minimum, entropy, hyphenated words, 4-char passwords, prefixed keys, masked placeholders, trailing Chinese punctuation, bracketed area/phone codes, single-space phone sequences), image size/relative path import recording and hidden-entry skipping, YOLO size refusal, unknown COCO images, open-work round preservation, assignment list/dispatch eligibility, and relative workbench sample names.
- **v0.19.0**: EXIF upright point/size mappings and legacy dataset reads, upright workbench/prelabel pixels, upright revisions/batches/splits, YOLO/COCO orientation roundtrips, upright export manifests, evidence extractor invalidation; per-project template locks and signed upgrades; open-work load limits and dispatch caps; named rework handovers; English Ask interpretations and coded refusal reasons; cloud prelabel budgets/estimates/reruns/failures/single-live-run; IoU matching, confidence tiers and calibration; accountable pass-through, holder-only drafts, widened pass-through signature, AI pre-review rules, sampling, risk-ordered queue, and pass-through triggerer review separation.
- **v0.20.0–v0.22.0**: one-sentence planning wording registry, full-sentence recipe guard, write-container provenance, permission-before-question, per-action preconditions, no-op plans, protected-task exclusion, plain-language cards, repair rounds; action-chain signatures, non-repeating resume, requester-only execution, signer binding; label-set drafting provenance and cost limits; endpoint-aware model routing; native skeleton tri-state validation, template-ID alignment, used-point deletion guard, EXIF/COCO topology/visibility/bounds/roundtrip protection, keypoint-only and mixed-empty-box metric exclusion; strict segment integers, project/upgrade source-probe checks, pre-filter format rejection, WebVTT unreviewed protection and mixed-metric degradation.

Subprocesses keep a 300-second timeout (900 seconds for full golden evaluation under shared workers); a single timeout reruns once in a fresh source copy, and a second timeout fails as an environment error rather than counting as `KILLED`.

## Evidence & Ask benchmarks (`eval-evidence`, `eval-ask`)

### `eval-evidence`

Generates a fresh 1,000-sample corpus in an isolated process and runs the production extraction DAG across the 15 queries in [contracts/evidence/questions.yaml](../contracts/evidence/questions.yaml) (4 near-duplicate, 4 conflict, 4 corrupt-image, 3 missing-annotation). Results are stored in `eval_runs` (`provider=evidence`) with the suite SHA-256; temporary corpora are discarded.

- **Default `prefix` mode (synthetic corpus)**: macro precision `0.336567 → 1.000000`, macro recall `0.933333 → 0.989542`; direct pairs `48/52` (precision `1.0`, recall `0.923077`); val-to-train pairs `47/51` (recall `0.921569`); `threshold_met=true`.
- **`--mode exact` (synthetic corpus)**: direct pairs `52/52` and val-to-train pairs `51/51` (both precision/recall `1.0`); macro precision/recall `1.0`.
- These figures measure the generated fixture and declared baselines only, not generalization to real datasets.

### `eval-ask`

Creates fresh isolated enterprise SQLite sources and evaluates [20 metric questions](../contracts/ask/questions.yaml) (`14 ok-`, `4 ua-`, `2 cl-`) at reference instant `2026-10-01T00:00:00Z` with 0.5% numeric tolerance, plus **23 knowledge/route cases** in both initial and reviewed states. No model call, token budget or charge is involved. `threshold_met` requires metric thresholds (≥13/14 answered, 4/4 refusals, 20/20 complete evidence) and both knowledge-route states to pass completely.

## Full repository gate & screenshot verification

Node.js 22 and Rust 1.96 are required for the full gate:

```bash
uv run python scripts/generate_semantic.py
uv run pytest tests/semantic
(cd web && npm ci && npm run build)
make check
uv run python scripts/check_readme.py
bash scripts/ci-check.sh
```

- `make check` runs `check-public`, `check-rust`, `check-python` (Ruff format + Ruff ALL + strict Pyright + `import-linter` + `check_size.py` + `check_boundaries.py` + `check_schema` + `check_web_tests.py` + pytest + ≥85% total / ≥90% module coverage), `check-scale`, `check-web` and `check_licenses`.
- `bash scripts/ci-check.sh` runs `make check` plus `scripts/check_readme.py` and `scripts/mutate.py`. Set `DATAKEEL_TEST_DATABASE_URL` to a fresh local PostgreSQL database (`CREATEDB` required) to repeat the gate on PostgreSQL; set `DATAKEEL_TEST_WORKERS=1` for serial execution. See [TEST_SPEED.md](TEST_SPEED.md) for sharded CI layout.
- Live acceptance & workers check against a running demo:
  ```bash
  uv run python scripts/verify_acceptance.py --base-url http://127.0.0.1:8765
  uv run python scripts/verify_acceptance.py --workers
  ```
- Reproducing the 52-shot UI screenshot matrix and UI smoke check (against an isolated demo home):
  ```bash
  cd web && npm ci && npm run screenshots -- http://127.0.0.1:8765
  # 13 pages × English/Chinese × light/dark → artifacts/screenshots/
  ```
  ```bash
  DATAKEEL_HOME="$(mktemp -d)" uv run datakeel demo --port 8773
  # In a second terminal from the repository root:
  npm --prefix web run smoke:ui -- http://127.0.0.1:8773
  # Screenshots and reports → artifacts/ui-smoke/
  ```

Offline boundaries: S3 relies on client-contract tests without contacting a live S3 endpoint; external LLM enrichment is verified with local HTTP fixtures only; interrupted task attempt artifacts remain on disk for inspection (automatic GC is deferred).
