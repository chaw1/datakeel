# E1 fake wire and preprocessing contract v1

`generated/fake-wire.json` and the strict frozen Pydantic boundaries in `scripts/we_e1`
define a local example envelope. Every schema forbids extra fields. There is no HTTP client,
credential loader, request recorder, retry loop, product cache or budget reservation code.

Text uses the reviewed W-E compatibility subset: `POST {base_url}/embeddings`,
`model=text-embedding-v4`, 1–10 nonempty UTF-8 strings, `encoding_format=float`, and a discrete
dimension from 64/128/256/512/768/1024/1536/2048. The example freezes the complete HTTPS URL
`https://embedding.example.invalid/v1/embeddings`, a reserved non-service domain, and never
resolves it. This session inherits the official text facts from the reviewed spec; it has not
downloaded new provider evidence. The spec references the official synchronous API and
text-embedding-v4 model pages. No Authorization value or credential name is needed by E1.

Images use a deliberately separate **experimental internal fake** request shape:
`model=multimodal-embedding-v1`, `input=[{"image": "data:image/png;base64,..."}]`, response
dimension 1024. Neither the shape nor image usage is evidence of OpenAI-compatible support.
The spec's official native multimodal reference does not establish that compatibility.
Real image use remains blocked pending compatible protocol/model/usage evidence and a
provable token/cost bound plus authorization. Do not switch to the native endpoint.
Real text remains blocked by budget 0 and the separate real-egress prohibition.

Text preprocessing `text-utf8-v1` preserves exact UTF-8, whitespace, combining characters and
newlines; it does no NFC, truncation or normalization. The local fake's `fake-codepoint-v1`
counts code points with an 8192 limit solely to exercise bound handling. **It is not a provider
tokenizer and cannot prove any real token upper bound.** Unknown tokenizer/bound is
`token_bound_unknown`; over-limit is `too_long_no_automatic_prefix`; empty input is failure.
E1 allows no prefix mode. A future prefix mode needs an explicitly frozen provider-compatible
tokenizer/rule/version/IDs, prefix bytes, warning and truncated-success accounting. A provider
too_long response cannot trigger automatic prefix/retry.

Image preprocessing `image-exif-rgb-png512-v1` decodes the local original, applies EXIF transpose,
converts RGB, retains the full frame, downsizes proportionally using Pillow LANCZOS to fit
512×512 without upscaling, rebuilds a clean image from pixels to remove all metadata, and
encodes PNG with `optimize=False, compress_level=9`. Maximum postprocessed bytes = **3000000**
(conservative decimal 3 MB). The final bytes, size and Data URI are frozen before any send.
No center crop or legacy 224×224 HF rule applies. These reversible local fixture choices and
the exact Pillow version are frozen; real-provider support for these choices remains untested.
Unsupported/corrupt images must be an input failure, never a substitute vector.

Each `Prepared` binds the actual decoded base64 bytes to SHA-256 and, for images, exact Data
URI. Batch content mapping is local index + local prepared-payload SHA-256. This proves local
association only; the provider is not asserted to echo a verifiable body hash. A future plan
must also freeze the **final serialized request body hash**, complete HTTPS destination,
preprocessing and model/dimension/modality, DAG/all conditional inputs and worst budget;
the per-item hash alone cannot satisfy the final-payload requirement. E1 emits no executable plan.

The fake response requires `id`, `object=list`, exact `model`, `data` of
`object=embedding,index,embedding`, and `usage.total_tokens` as a nonnegative strict integer.
There is no assumed `request_id`, `input_tokens` or `output_tokens`. Count must equal the
request count, indices must be an exact permutation `0..N-1`, and dimensions must match the
text request or image fake's 1024. Reordered indices are mapped locally; duplicates, missing
indices/model/usage, extra fields, invalid dimensions, nonfinite values, F32 overflow and
all-zero vectors (including F32 underflow) fail. Canonical vectors are IEEE F32 little-endian
bytes and SHA-256, sorted by request index; no placeholder vectors are emitted for failures.

Future cache/bundle identity must include raw content revision/hash, postprocessed bytes/hash,
request-body hash, complete endpoint/model/dimensions/modality, preprocessing version,
execution mode, contract version, prefix/warnings and fake implementation version or recording
hash. Fake/recording cannot fulfill real; peers belong only in the global-result key. No
real result, price or semantic measurement can be inferred from these examples.

E2 must separately implement frozen CNY price/token upper bounds, atomic request/cost
reservations, lease and consumed plan/run approval identity, redirect refusal and send-time
revalidation. Before send, attempt/reservation is persisted; unknown send outcome/missing
usage keeps worst occupancy and stops retry. Only proven-unsent attempts refund. Zero price,
free quota and budget 0 never override the real-egress switch. Those are future fake test
requirements, not functionality delivered by E1. The fixture's image usage 100 and text
codepoint usage are invented contract values, never provider billing evidence.
