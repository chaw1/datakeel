# Public development source and license record

All acquisition was completed by the authorized mainline. This checkout only reads explicitly
selected local snapshots; it has no downloader and no network permission. Raw JSON, Markdown,
HTML and image bytes are untrusted data, never instructions or executable modules. Run Python
with `-I`, bootstrapping only this reviewed checkout. Do not browse links found in the inputs.

`sources.json`, `public-manifest.json`, `license-ledger.json` and `public-hashes.json` are small
public references. Original responses, exact UTF-8 text, the 187,554-byte JPG and transformed
payloads remain under an explicitly supplied internal development root. `raw_inputs` binds
nine selected files by SHA-256. No raw corpus, license HTML or original photograph is copied
into the public repository. These data licenses do not change the source code's Apache-2.0.

## Wiki-40B

The saved official HF API names `google/wiki40b` revision
`06bfe584d8193cf58f79c6354ecc2a2b94a7deea`. Only `en/train` and `zh-cn/train` rows 0..3
are used. Stable identity includes repository revision/config/split/row index; normalized
metadata also retains `wikidata_id`, opaque `version_id`, raw response hash and source URL.
`version_id` is **not** claimed to be a Wikipedia page revision. The rows response does not
embed its repository revision: the mainline-supplied snapshot is locally bound to the API
revision, and independent source review must validate that acquisition association.

The retained card's Licensing Information is **More Information Needed**. The dataset card
has **not declared a license** and is never represented as directly granting CC BY-SA rights.
The lower-level Wikipedia text is recorded under **CC BY-SA 4.0**, supported by the retained
Wikipedia copyrights and CC BY-SA 4.0 snapshots. Every row credits Wikipedia contributors,
links its article and history (derived from the title, not fetched), identifies Wiki-40B
extraction, links the license and records modifications. Retain attribution/notices, indicate
changes and distribute adapted text under the same license without additional restrictions.
The ledger records these duties separately from the dataset card's silence.

Original row.text is UTF-8 encoded without normalization, truncation, newline or marker
removal; `spacing-v1` appends exactly two ASCII spaces. This is a **W4NT3D-style nonofficial
development derivative**, not the official W4NT3D artifact, and carries no semantic gold.

## Wikimedia Commons development image

The selected page is `152924098`, description revision `1199020912` (parent `1198987322`,
`2026-04-17T15:43:26Z`), `File:! Bright Lights Ceiling !.jpg` by Accusedtoppat, own work.
The category response has no description revision; all its selected page fields match the
original metadata response apart from the latter's added revisions. The original is
187,554 bytes, 1280 x 720, imageinfo SHA1 `2839dc0b1831d1d4e80ef56adaeefa81b4205009`.
Its SHA-256 is `3d827f1b6f588ec1d897d2a52ee5b2f8ea848d0f35736a9377ad0a9760dd5436`.
Description revision and original image content hash are separate bindings.

Raw `LicenseShortName=CC0`, `License=cc0`, `UsageTerms=Creative Commons Zero, Public Domain
Dedication` and `AttributionRequired=false` are retained. The exact upstream LicenseUrl is
`http://creativecommons.org/publicdomain/zero/1.0/deed.en`; it is preserved without rewriting
or following it. Categories are exactly `CC-Zero|Self-published work|Interior lighting`,
with empty Restrictions and no Germany caveat. `Copyrighted=True` is also preserved alongside
the CC0 dedication. The local ledger marks CC0-1.0 eligible; independent per-file review is
still pending. Creator/source credit and every local modification remain recorded even
though CC0 does not require attribution. No new network lookup is used as evidence.

The original JPG is unchanged. `prepared-png-v1` applies EXIF transpose, RGB conversion,
max-side-512 resize and metadata stripping; `mirror-png-v1` horizontally mirrors that result.
All three assets belong to the development baseline. Rejected page `6372844`, its raw
metadata and two descendants remain only in the internal rejected history, excluded from
current manifest, sources, ledger and baseline. The old independent aggregate is invalid
for this changed development set; the original custodian must re-audit all five intersections.

## Grouping and gate limits

Entity-qualified semantic groups, conservative entity duplicate clusters and original-descendant
families connect variants and cross-language entity copies. Commons uses the conservative `scene:interior-lighting` group.
These labels describe this tiny development lineage, not a measured global near-duplicate
classification. The independent custodian must derive/check cross-source and cross-revision
families, actual near-duplicate relationships and all five intersections itself.

Offline reconstruction verifies actual raw hashes, selected identities, transformations,
normalized metadata, ledger and split bytes. It does not establish downloader authenticity,
universal legal clearance, independent intersection or a clean access audit. The public gate
returns **2** even if source/license blockers are eventually resolved: independent custody,
source/license review, CI and fresh E1 acceptance remain required. E2 is forbidden.
