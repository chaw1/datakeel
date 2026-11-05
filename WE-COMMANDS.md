# W-E E1 offline reproduction

Run from this reviewed checkout with prepared Python 3.12 tools. Set `WE_E1_PYTHON`,
`WE_E1_TOOLS` (tool bin directory), and `WE_E1_DEVELOPMENT_ROOT` to the explicitly authorized
local **development** snapshots. Do not point any command at held-out material. No command
has network permission; do not install dependencies, browse evidence URLs or run downloaders.
Python uses `-I`; only the reviewed checkout is explicitly added to its import path:

```sh
e1() {
  "$WE_E1_PYTHON" -I -B -c 'import runpy,sys; module=sys.argv.pop(1); sys.path.insert(0,"."); runpy.run_module(module,run_name="__main__")' "$@"
}
e1 scripts.we_e1.generate --check
e1 scripts.we_e1.public_generate --development-root "$WE_E1_DEVELOPMENT_ROOT" --check
env PYTHONHASHSEED=1 "$WE_E1_PYTHON" -I -B -c 'import runpy,sys; sys.path.insert(0,"."); runpy.run_module("scripts.we_e1.generate",run_name="__main__")' --out artifacts/we/determinism-a
env PYTHONHASHSEED=97 "$WE_E1_PYTHON" -I -B -c 'import runpy,sys; sys.path.insert(0,"."); runpy.run_module("scripts.we_e1.generate",run_name="__main__")' --out artifacts/we/determinism-b
diff -ru artifacts/we/determinism-a artifacts/we/determinism-b
e1 scripts.we_e1.verify --development-root "$WE_E1_DEVELOPMENT_ROOT"
e1 scripts.we_e1.verify --development-root "$WE_E1_DEVELOPMENT_ROOT" --public-gate
e1 pytest -q tests/evaluation --basetemp artifacts/we/pytest
"$WE_E1_TOOLS/ruff" format --check .
"$WE_E1_TOOLS/ruff" check .
"$WE_E1_TOOLS/pyright" --pythonpath "$WE_E1_PYTHON" scripts/we_e1 tests/evaluation
git diff --check
```

Run each validation separately, recording its real exit and output hash. All listed checks
require exit 0 **except public-gate, which must remain exit 2**. It reconstructs the real
source/license evidence but never grants independent acceptance. Without the explicit local
development root, normal verification checks only public schemas/fake wire and emits a
blocked export; it cannot claim real provenance validation.

Also reconstruct `public_generate` in separate processes with `PYTHONHASHSEED=1/97`, writing
the four small public files to separate ignored `--out` directories; recursively diff them.
The derived internal files must remain identical too (hash before/after, or use `--check`).
The task journal records the exact commands used. Generated raw text and image variants stay
inside the development root, not the public output directories.

Run repository import-boundary, storage-boundary, size and public-content scans with the same
prepared tools and isolated Python checkout bootstrap. Run `UV_OFFLINE=1 CARGO_NET_OFFLINE=true npm_config_offline=true make check` with local
caches only; a missing dependency is a failure, never permission to fetch it. Required full
gate and dual-stack CI remain unverified until their complete runs succeed;
do not replace them with targeted results or begin E2.

Expected reports: `artifacts/we/W-E-A1.json`, `W-E-A9.json`, `E1-exit.json`, and
`development-public-evidence.json`, copied into the internal handoff. The last contains nine
public rows (eight text originals and one locally CC0-eligible image), with no restricted candidate, with real manifest/ledger hashes. The prior independent aggregate is unusable after image
replacement; the original custodian must bind its new audit to these hashes.
No independent summary is created or consumed by this CLI. Source/license integrity,
independent review, five intersections, audit, CI and E1 permission are separate facts.

Worktree scope: `CHANGELOG.md`, `WE-COMMANDS.md`, `contracts/we-e1/**`, `scripts/we_e1/**`,
`tests/evaluation/**`. No staging, commit, push, publication or E2 is authorized.
