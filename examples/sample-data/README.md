# Generated sample data

Run `uv run python -m examples.generate --samples 1000` to create 1000 paired
samples and `gold.json` here. Use `--output /path/to/generated-data` to select
another directory. Every sample has `train|val/scene-NNNN/image.png` and
`caption.txt`; `annotations.json` contains the image width/height and a COCO-style
`annotations` array with `category` and `[x, y, width, height]` bounding boxes.

The fixed seed yields 800 training and 200 validation samples, with 50 injected
cross-split near-duplicate pairs (crop, resize, or noise), 50 caption/annotation
gaps, 10 corrupt images, and 30 missing annotation sidecars. Gap cases overlap
the duplicate validation targets; missing annotations and corrupt files occupy
separate samples. A separate three-image chain adds two gold pairs: its dHash
distances are A-B = 6, B-C = 6, A-C = 12, with an eight-bit distance threshold.
The endpoints must never be linked by transitive closure. This gives 52 total
gold pairs, 51 across splits. Counts round down for smaller requested datasets;
the controlled chain is included when at least 100 samples are requested.

`gold.json` records all sample paths, expected concepts and scene states,
annotation gaps, missing/corrupt cases, and injected pairs. It is the evaluation
denominator, never an extraction input. Repeating a command produces identical
bytes, including gold; generated files are ignored by Git and can be recreated.

The original `datakeel.sample.generate_samples` entrypoint remains available for
the earlier 200-image/200-text fixture, including its two deliberate empty texts.

All content is generated under the project's Apache-2.0 license. No binary
fixture, downloaded image, or external business data is required.
