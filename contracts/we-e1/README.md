# W-E E1 contracts and real public development evidence

This batch freezes development inputs and fake wire contracts. It does not measure encoder
quality or implement E2–E5. The authoritative W-E spec and amendments govern.

| Artifact | Current evidence |
| --- | --- |
| `generated/manifest.json` | 24 synthetic contract fixtures; never substitutes for public rows |
| `public-manifest.json` | 8 real Wiki-40B originals and one locally CC0-eligible Commons image; 19 original/variant assets |
| `sources.json` | Fixed HF revision/config/split/rows and Commons page/revision, original hashes and metadata references |
| `license-ledger.json` | Per-original attribution, duties, changes, raw evidence and independent-review status |
| `public-hashes.json` | SHA-256 of small public artifacts; raw input hashes are in the public manifest |
| Development splits | Connected source/content/entity/cluster/family components; tune/validation only |
| Source/license gate | Real integrity reconstructible offline; text card silence preserved; image CC0 fields checked locally |
| Independent custody | Prior aggregate invalidated; new five-dimensional comparison and access audit pending |
| E1 exit / E2 | Blocked / forbidden |

See [sources and licensing](SOURCES.md), [isolation](ISOLATION.md),
[fake wire protocol](PROTOCOL.md) and [reproduction commands](../../WE-COMMANDS.md).
Raw responses and content remain in the explicitly authorized internal development root.
Only small manifests/hashes/attribution are public. No dependency, runtime endpoint or real
model call is added. The generator reads downloaded content as data only and never fetches
additional sources. Internal reports are local evidence, not independent approval.

`generate` freezes synthetic fixtures and schemas; `public_generate` reconstructs actual
public development data separately. Both pin Pillow and generator versions. The finite grid
in `search-space.json` remains unselected: duplicate cosine `{0.8, 0.9, 0.95}`, DBSCAN eps
`{0.05, 0.1, 0.2}`, min_samples `{2, 3, 5}`, gap `{0.5, 0.7, 0.9}`, and text dimensions
64/128/256/512/768/1024/1536/2048. Image dimension remains 1024. Bounds remain 5000 samples
and 250000 candidate/reference comparisons. No grid value is an accuracy threshold.

Future evaluation retains direct `i<j` duplicate pairs, deterministic F64 DBSCAN border rules,
`T union R` embedding and `T minus R` gap semantics, and the reviewed single independent
campaign. No FAISS dependency, semantic metrics, cloud latency or usage claim is made here.
Full `make check`/CI evidence is still required before E1 acceptance. Offline-only checks
cannot replace unavailable dependencies, independent custody or fresh acceptance. No threshold
or check is relaxed.
