# Training splits and exports

[中文](TRAINING.zh.md)

Open a dataset's **Versions** tab and expand **Training sets**. Select an immutable
source version, set train/validation/test proportions, a seed, optional stratification
and a metadata group field. Preview reads the files and computes distributions without
saving. **Save immutable split** creates a named, version-owned snapshot. Repeating the
same name and policy returns that snapshot; changing its policy requires another name.

Set `test=0` for two sets, for example `train=0.8, val=0.2`. Proportions must sum to one.
Every sample appears once. The class table counts each label once per sample, so
multilabel totals can exceed the number of samples. The adjacent meters show class
prevalence. Select another saved split to compare its distribution and assignments.

## Reproducible grouping and stratification

Single-label independent samples use seeded stratified allocation with largest-remainder
integer quotas. Multilabel samples use rare-label-first iterative stratification.
Groups and connected duplicate clusters are indivisible; an entire connected component
receives one split. A metadata field can be nested, for example `capture.session` or
`metadata.capture.session`. A missing or null group value does not join unrelated samples.

Group isolation takes priority over exact ratios. A group larger than a validation
target, or mutually constrained multilabel groups, can make requested class proportions
mathematically impossible. Inspect the measured counts before training. The seed, full
policy, algorithm version, member identities, source hashes and annotations are frozen.
Later annotation imports do not rewrite an existing split. Create a new named split to
use revised annotations.

## Leakage evidence

New splits avoid duplicate edges by default and always preserve explicit groups.
Choose **Existing directory assignments** to inspect imported `train/`, `val/` and
`test/` memberships without changing them. The report lists direct cross-set pairs,
both sample IDs and split names, the signal and its distance:

| Signal | Rule |
| --- | --- |
| Exact | Equal SHA-256 content hashes |
| Image | 64-bit dHash, Hamming distance at most 8 by default |
| Text | 64-bit simhash, Hamming distance at most 3 by default |
| Group | Equal non-null values of the configured metadata group field |

Image and text thresholds are configurable from 0 to 64. Hash comparison uses the
existing optional Rust backend when available and exact Python comparison otherwise;
it does not use lossy prefix blocking. A–B and B–C edges group all three samples while
the report retains only measured direct edges. Text normalization applies Unicode NFKC,
case folding, whitespace and punctuation removal, then weighted character trigrams.
Thus variants differing only in those normalized characters have distance zero.
Empty normalized text supplies no text-similarity signal. These hashes are similarity
heuristics; inspect pair evidence rather than interpreting them as semantic identity.

Flat images need an additional color confirmation to avoid dHash collisions: on a
32×32 RGB thumbnail, an image is low texture when every channel's standard deviation
is below 3. If either image is low texture, both must be low texture and their mean RGB
values must differ by at most 12 per channel. Textured images retain the configured
dHash threshold. Resizing and JPEG recompression of a flat image remain comparable.

## Training archives

Select a saved split, a format and, when multiple reviews exist, an explicit annotator.
**Review export plan** uses the existing `export_dataset` controlled action. Review its
frozen version, split, object/byte budget and effects, then use the normal approval and
execution controls. A successful receipt exposes **Download training archive**. Current
source export permissions are rechecked on every download. Export receipts enter lineage.

| `format` | Archive layout and annotation convention |
| --- | --- |
| `coco` | `images/<split>/` and `annotations/instances_<split>.json`; integer IDs, absolute `[x,y,width,height]`, area, `iscrowd=0` |
| `yolo` | `images/<split>/`, matching `labels/<split>/*.txt` and relative `data.yaml`; zero-based classes, normalized center/width/height |
| `imagefolder` | `<split>/<class>/<image>`; requires exactly one classification label per image |
| `hf_imagefolder` | Images plus split-local `metadata.jsonl` with relative `file_name`, labels and detection objects; root `categories.json` |
| `text_jsonl` | `<split>.jsonl`; exact text, labels and half-open character-offset spans |

Images with no detection boxes have an empty YOLO label file and remain in COCO images.
Invalid or out-of-bounds boxes are refused. ImageFolder rejects missing or multiple class
labels. Text offsets count Unicode characters, not UTF-8 bytes or UTF-16 code units, and
the exporter validates them against the original unnormalized text.

`MANIFEST.json` records the source version, optional release, split ID, seed, format and
format version, total and per-split file counts, annotation counts and each source hash.
Source filenames are replaced with safe stable names. Tar members are sorted, with
fixed ownership, permissions and timestamps. `.tar.gz` and `.tgz` also use a fixed gzip
header. The same version, saved split, annotator, format and archive compression produce
identical bytes. Export destination and action time are excluded. No training-library
runtime dependency is required.

## CLI, Agent and HTTP

```sh
datakeel training distribution DATASET --version VERSION --train 0.8 --val 0.1 --test 0.1 --seed 42 --json
datakeel training create DATASET --version VERSION --name baseline --group-field capture.session
datakeel training list DATASET --version VERSION
datakeel training leakage DATASET --version VERSION --split-set SPLIT --json
datakeel training compare DATASET LEFT_SPLIT RIGHT_SPLIT
```

Without `--split-set`, `distribution` previews a generated split and `leakage` inspects
directory assignments. Omitting `--version` selects the latest immutable version and
returns its exact ID. Agent and MCP discover `training_distribution` and
`training_leakage`; both are read-only, with the same typed measurements as the CLI.

The API prefix is `/api/datasets/{dataset}/versions/{version}/training`:

- `GET/POST /splits` lists or saves named sets; `POST /preview` only computes.
- `GET /splits/{id}` reads a set; `GET /splits/{id}/leakage` checks its frozen signals.
- `POST /leakage` checks a preview; `GET /compare?left=ID&right=ID` compares saved sets.
- `POST /import-annotations` imports standard COCO or typed YOLO labels into a new
  immutable annotation review batch for that version. An explicit COCO filename map
  resolves renamed or ambiguous images. YOLO supplies category names, sample IDs,
  source dimensions and per-image label text.

Prepare exports through `POST /api/actions/export_dataset/prepare` with `dataset_id`,
`version_id` (or `release_id`), `split_set_id`, `format`, optional `annotator_id` and
`destination`. Existing metadata formats retain their original behavior. The full typed
request schemas and examples are in the local [API reference](http://127.0.0.1:8765/api/docs).

Format references: [COCO](https://cocodataset.org/#format-data),
[Ultralytics detection](https://docs.ultralytics.com/datasets/detect/),
[Hugging Face imagefolder](https://huggingface.co/docs/datasets/image_dataset).
