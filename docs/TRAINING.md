# Training splits and exports

[中文](TRAINING.zh.md)

Open a dataset's **Versions** tab and expand **Training sets**. Select an immutable
source version, set train/validation/test proportions, a seed, optional all-label stratification
and a metadata group field. Preview reads the files and computes distributions without
saving. **Save immutable split** creates a named, version-owned snapshot. Repeating the
same name and policy returns that snapshot; changing its policy requires another name.

Set `test=0` for two sets, for example `train=0.8, val=0.2`. Proportions must sum to one.
Every sample appears once. The class table counts each label once per sample, so
multilabel totals can exceed the number of samples. The adjacent meters show class
prevalence. Select another saved split to compare distributions. Use the CLI or
comparison API below to inspect changes in sample assignments.

## Reproducible grouping and stratification

Single-label data uses seeded largest-remainder quotas and an integer transport solver.
Multilabel data uses iterative stratification: allocate the rarest remaining label first,
update the desired counts for every label on each selected sample, then refine whole-group
assignments against all label quotas and class prevalence together. Labels are deduplicated
and sorted for computation; saved members retain the original labels and complete annotations.
Each export writes the annotations supported by its format.

For feasible inputs, the targets are at most one sample from each label's requested split
count, and at most two percentage points from global prevalence for every category with at
least 50 samples. Refinement checks both limits before overall split-size proximity, with
up to 16 additional deterministic seeded starts for multilabel data. This is a bounded search,
not a general integer-feasibility proof. Inspect the actual distribution for your data.

Groups and connected duplicate clusters are indivisible; an entire connected component
receives one split. Their isolation takes priority over balance and exact ratios. A metadata
field can be nested, for example `capture.session` or `metadata.capture.session`. A missing
or null value does not join unrelated samples.

Small integer sets can make the two numerical targets incompatible even without groups.
For example, 159 samples with disjoint class counts 55/52/52 and an additional label on every
sample, at 80:10:10, cannot meet both limits. The universal label requires train size 127–128
and validation/test size 15–16. A size-16 set cannot represent class 55/159 within two percentage
points (neither 5/16 nor 6/16 works), so both small sets must have size 15, forcing train size
129. A group larger than a validation target can also make the target unattainable. A search
that misses a target is not by itself evidence of impossibility. Counts remain visible;
groups are never split and the requested policy is never silently changed.

New splits use algorithm `1.3-iterative-text`; its version is included in the split identity.
The seed, full policy, member identities, source hashes and annotations are frozen. Existing
named snapshots, including `1.2-primary-no-text`, are read without recalculation or replacement.
Repeating the same name and policy returns that exact snapshot. Use a new name for the new
algorithm or revised annotations.

## Leakage evidence

New splits avoid duplicate edges by default and always preserve explicit groups.
Choose **Existing directory assignments** to inspect imported `train/`, `val/` and
`test/` memberships without changing them. The report lists direct cross-set pairs,
both sample IDs and split names, the signal and its distance:

| Signal | Rule                                                         |
| ------ | ------------------------------------------------------------ |
| Exact  | Equal SHA-256 content hashes                                 |
| Image  | 64-bit dHash, Hamming distance at most 8 by default          |
| Text   | 64-bit normalized-text simhash, Hamming distance at most 3 by default |
| Group  | Equal non-null values of the configured metadata group field |

Image and text thresholds are independently configurable from 0 to 64. Hash comparison uses the existing
optional Rust backend when available and exact Python comparison otherwise; it does not
use lossy prefix blocking. A–B and B–C edges group all three samples while the report
retains only measured direct edges. Image hashes are similarity heuristics; inspect pair
evidence rather than interpreting them as semantic identity.

Text hashing applies Unicode NFKC normalization and case folding, then removes Unicode
punctuation, ASCII punctuation/symbols, whitespace and zero-width U+200B/U+200C/U+200D/U+2060/U+FEFF, then applies NFKC again so that
combining characters separated by removed formatting recompose. It hashes character trigrams with SHA-256 and computes a weighted
64-bit simhash; shorter nonempty text is one feature. Changes confined to case, whitespace or
punctuation therefore have distance zero, including changes inside words, and are recalled
even with threshold zero. Empty normalized text has no simhash; byte-identical files still
match SHA-256. These transformations affect only comparison, never exported source text or
character offsets. Short texts, rearranged templates with the same trigram multiset, and text that becomes
identical after space or symbol removal (for example, `C++` and `C`) can collide: this signal is a formatting/similarity check, not semantic equivalence.
A threshold of 64 matches every pair with a text hash and is usually unsuitable.

Byte-identical text files produce an exact SHA-256 pair only; the same pair is not
counted again as text near-duplication. Formatting variants with different source
bytes still produce the text signal.

`checked_signals` states what a report actually checked. A saved `1.2-primary-no-text` snapshot
keeps its original three signals and does not read source files to invent missing text hashes.
Create a new named split or preview to compute the new text signal. A clean report applies
only to the listed signals and configured thresholds.

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

| `format`      | Archive layout and annotation convention                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `coco`        | `images/<split>/` and `annotations/instances_<split>.json`; integer IDs, absolute `[x,y,width,height]`, area, `iscrowd=0`       |
| `yolo`        | `images/<split>/`, matching `labels/<split>/*.txt` and relative `data.yaml`; zero-based classes, normalized center/width/height |
| `imagefolder` | `<split>/<class>/<image>`; requires exactly one classification label per image                                                  |
| `hf_imagefolder` | `<split>/<image>` and `metadata.jsonl`; lossless scalar metadata, described below |
| `text_jsonl`  | `<split>.jsonl`; exact text, labels and half-open character-offset spans                                                        |

Reviewed-empty images (`boxes=[]`) have an empty YOLO label file and remain in COCO images.
Missing box reviews (`boxes=null`) are refused for detection exports, rather than treated
as negative examples. YOLO requires at least one explicit detection category across the
selected samples. COCO can represent a reviewed all-empty dataset with no categories;
that is a valid interchange document, not a useful zero-class training task.
Invalid or out-of-bounds boxes are refused. ImageFolder rejects missing or multiple class
labels. Text offsets count Unicode characters, not UTF-8 bytes or UTF-16 code units, and
the exporter validates them against the original unnormalized text.
ImageFolder accepts the default torchvision suffixes: `.jpg`, `.jpeg`, `.png`, `.ppm`,
`.bmp`, `.pgm`, `.tif`, `.tiff`, `.webp`. YOLO accepts Ultralytics image suffixes:
`.avif`, `.bmp`, `.dng`, `.heic`, `.heif`, `.jp2`, `.jpeg`, `.jpg`, `.mpo`, `.png`,
`.tif`, `.tiff`, `.webp`. Both reject other suffixes, including GIF, instead of producing
archives whose images the standard loader would ignore. Sources are never transcoded.
Imported coordinates that exceed a pixel boundary only by floating-point roundoff
(at most four ULPs of the image extent) are clamped to that boundary; real overflow is refused.

HF imagefolder writes `file_name` relative to each split's `metadata.jsonl`, with scalar
`sample_id`, `annotator_id`, `width`, `height`, `labels_json` and `boxes_json` columns. Load the
unpacked directory with `datasets.load_dataset("imagefolder", data_dir="package")`; HF names
`val` as `validation`. Decode `labels_json` and `boxes_json` with `json.loads` to recover the
original category strings and absolute pixel `x1,y1,x2,y2` boxes. JSON `null` means unreviewed;
`[]` means reviewed empty. JSON text columns keep the inferred schema identical across splits
containing only empty annotations versus populated ones, without artificial examples. The
archive includes these instructions in `README.md`. No `datasets` dependency is added.
COCO, YOLO and HF imagefolder exports share one EXIF orientation check: only absent or
identity (1) orientation is accepted. Values 2–8 can rotate or mirror decoded pixels and
invalidate the frozen raw-pixel boxes or dimensions. Normalize these sources and their
annotations together before importing them again. The exporter neither transcodes pixels
nor silently rewrites coordinates, and a refused export produces no archive.

| Orientation policy | Benefit | Required trade-off |
| ------------------ | ------- | ------------------ |
| Reject nonidentity EXIF (chosen) | Preserve source bytes and the frozen annotation frame across all three formats | Oriented sources must be normalized before import |
| Transpose pixels and transform boxes | Export oriented sources directly | Rewrite pixel bytes, dimensions and every box for each rotation/mirror, with new provenance semantics |

Rejection keeps the existing HF policy and the source-byte export contract consistent.
Pillow's [`exif_transpose`](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html#PIL.ImageOps.exif_transpose)
applies the orientation transform and removes its metadata; adopting it here would also
require corresponding coordinate transforms rather than a pixel-only change.

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

Format references: [HF imagefolder](https://huggingface.co/docs/datasets/image_dataset),
[COCO](https://cocodataset.org/#format-data),
[Ultralytics detection](https://docs.ultralytics.com/datasets/detect/),
[Ultralytics image formats](https://docs.ultralytics.com/modes/predict/#image-and-video-formats),
[torchvision ImageFolder source](https://docs.pytorch.org/vision/stable/_modules/torchvision/datasets/folder.html).
