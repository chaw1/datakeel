# Annotation workbench

Open **Annotation workbench** from the sidebar (`#/labeling`). The original Workbench overview remains available. Choose a production project and task package. Personal projects have **My data**; group and team projects expose **My tasks**, **Review queue**, and **Project cockpit** according to the effective server scopes. Create projects, published label sets, and packages with the existing production CLI; `datakeel production demo` creates a personal box project with generated predictions.

The module bar shows the project, task package, and authoritative production progress. The operation bar names the open file and contains save, undo, redo, submission, and task navigation. While a task is open the page drops the marketing heading and footer, and the work area fills the window height below the two bars; it follows window resizes. Image tools and zoom controls sit in a narrow left rail. The right drawer (properties, immutable revisions, review comments, guide) collapses with **Hide details**, which widens the canvas. Task lists, the review queue and the cockpit show and search tasks by file name. Datasets record only the base file name at import, so a path inside the dataset can be shown once import records it.

Boxes and polygons use their label's configured colour; labels without a colour take a fixed eight-colour palette in label order (`--label-1`…`--label-8`, light and dark values checked by `check:contrast`). Each shape carries its label name in a chip that keeps a constant screen size at any zoom.

## Editing and templates

Templates use the existing versioned `ProductionTemplate` catalog object. A project's published label-set version supplies stable category identities. Without a template, a project uses the box component. Configure the primary `annotation_type` and optional `component_config`:

```json
{
  "components": ["box", "classification"],
  "label_mode": "multi",
  "shortcuts": {"cat": "1", "dog": "2"},
  "guidelines": "Label only visible objects."
}
```

Templates may also define typed attribute fields (`attributes`): `boolean`, `enum`, `multi_enum`, `number` (optional range) and `text`, each with Chinese and English names, `required`, a default and a `target` of `object` (every box, polygon and span) or `record` (the whole item). The workbench renders them as native form controls; required fields block both autosave (status "Not saved · fill in the required attributes") and submission, naming the shape and field. The server applies the same rules and returns 422 naming the field, so a bypassing client is rejected too. Templates without fields behave as before; raw JSON attributes are only offered to project managers under **Advanced**. See [PRODUCTION.md](PRODUCTION.md) for the field schema and its comparison with CVAT, Label Studio and Labelbox.

Supported components are `box`, `polygon`, `classification`, and `text_span`. Label names remain user content; stored categories are label IDs. Template configuration is available to project managers; saving updates the existing catalog revision through `create_label_set`. P29's template references retain their existing shared-template semantics: projects referencing the same template ID use its current catalog revision. Template name, revision, and label-set version are visible in the drawer.

Every field and operation is keyboard reachable. Press `?` within an editor to show the shortcut table. `Ctrl/⌘+S` saves, `Ctrl/⌘+Enter` submits, `Ctrl/⌘+Z` undoes, `Ctrl/⌘+Shift+Z` or `Ctrl/⌘+Y` redoes. `Alt+N`/`Alt+P` navigates tasks after flushing pending changes; presses made while a page or task is still loading are queued and replayed in order, so rapid presses across page edges land on the right task. Text fields retain native text undo.

- Boxes: `B` adds; arrows move one source pixel, Shift+arrows ten; `R` switches the arrows to the right/bottom edges, then the left/top edges, then back to moving (the rail states the current mode); `Ctrl/⌘+D` copies; Delete removes. Dragging and transform handles use source-image pixel coordinates. Coordinate fields and JSON properties provide an accessible alternative.
- Polygons: `P` starts; arrows move the cursor one source pixel (Shift: ten); Space or a click adds a point, also on top of an existing shape; Enter closes; Escape cancels. Outside drawing, clicking a shape selects it. Arrows move the whole polygon; `R` switches them to the selected point. Backspace deletes a point when a valid polygon remains.
- Classification: radio/checkbox controls support Tab, Space, and arrow keys; label shortcuts also work. `label_mode` chooses single or multiple labels.
- Text spans: select characters with Shift+arrows or the pointer, then Enter. Numeric start/end fields also work. Nested spans are retained. Offsets count original Unicode codepoints, including astral characters and CRLF source offsets, matching Python.

## Saving and review

Edits are retained in a local draft immediately and saved through `save_revision` after a 500 ms debounce. Saves are serialized; an edit made while a request is pending remains dirty until its own save completes. Draft keys include actor, project, and task. A same-tab workspace snapshot restores the selected task across reloads. Current server identity is verified before restored drafts can sync. Browser document availability during a complete offline reload depends on the hosting/browser cache; a service worker is not installed.

The next two tasks, revision payloads, and decoded images are prefetched. Task navigation waits for a pending save; offline errors and conflicts keep the current draft visible. The undo timeline has no fixed step cap, but available device memory/storage still bounds practical history. Unsaved local state survives reload; completed undo timelines are session-local.

A 409 never silently replaces a revision. **Reload server revision** discards the local changes only after the explicit choice; **Overwrite with my edits** reads the current head and attempts a compare-and-swap save. Another concurrent write can cause another visible conflict. Storage failures show a warning. Returning online automatically retries pending edits.

## Open tasks refresh themselves

An open task polls `GET /api/production/tasks/{id}/status` every 5 seconds; a hidden tab slows to every 30 seconds and reads again as soon as it is shown. Lease renewal continues while hidden. Within that interval the page says when the task was returned for rework, changed state elsewhere, or got a newer revision from someone else, and offers **Reload server revision** or **Back to list**; local unsaved drafts are kept either way. A return also counts when the page's own submission read already shows the task pending in the next round, and the notice quotes the reviewer's notes. Team-tier leases renew automatically on open and then every 2 minutes, or every third of the lease when the lease is shorter (the length the server granted on the last renewal), through the `heartbeat` action, and the operation bar shows the time left. A failed renewal is shown with **Renew now** and retried. When the lease expires, the holder's assignment is reclaimed, or a save is refused for an expired lease, editing locks, the page says "This task was taken back", and the draft can be exported as JSON. **Back to list** then leaves at once without waiting for a save that can no longer succeed, and reloads the list so it shows the new holder and state. A 409 caused by a concurrent change ("Action target state changed after preparation") is shown as "Someone else just changed this task" with **Try again**; raw server text is not shown.

| Option | What it needs here | Delay | Cost and failure modes | Decision |
|---|---|---|---|---|
| Polling a small status read | One indexed read per open task; works through every proxy and with SQLite | ≤ poll interval (5 s, inside the 10 s budget) | One request per tab every 5 s; nothing to reconnect | **Chosen** |
| Server-sent events ([HTML Standard](https://html.spec.whatwg.org/multipage/server-sent-events.html), [MDN EventSource](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)) | A long-lived response per tab plus a change feed every API process can see (database notifications or a broker) | Near-immediate | Over HTTP/1.1 browsers allow about six connections per host, shared by all tabs ([EventSource pitfalls](https://textslashplain.com/2019/12/04/the-pitfalls-of-eventsource-over-http-1-1/)); buffering proxies delay events; reconnect and missed-event replay must be built | Not now |
| WebSocket | Same change feed plus a bidirectional protocol and authentication on upgrade | Near-immediate | Most moving parts; no benefit for one-way notices | Not now |

Polling reuses the existing read path and access checks and adds no dependency. If push is needed later, SSE on top of a database change feed is the smallest step; the page logic only needs a different source for the same status object.

Personal submission approves the task directly. Group reviewers approve or return the exact current revision with an issue; rework remains with the original annotator. The queue orders by rework rounds, model confidence, prelabel difference, then stable task ID. Prelabel difference is one minus multiset Jaccard agreement over exact labeled shapes/attributes or class values, not a measured model-accuracy score. The cockpit displays P29 counters, workload, confidence distribution, annotation agreement, approved-reference prelabel exact-match rate, and repeated-rework IDs without maintaining a second fact store. Finalization first displays a frozen action plan in plain words: how many approved tasks will be finalized, into which dataset as a new version, and how many unapproved tasks block it; the digest and raw parameters stay under **Details**. A separate **Approve and finalize project** click signs and executes it.

Team-tier projects add to the cockpit: each package's acceptance state and latest sampling result (read from `package_acceptance`); **Accept package**, where the manager marks each sampled task, prepares an `accept_package` plan that states the outcome, then signs it; **Dispatch by skill**, which previews per-person counts and the reason each unassigned task was skipped (`dispatch-preview`), then prepares and signs an `assign_tasks` plan with `strategy: "skill"`; and **Who holds what** (`lease_status`), where a manager takes a task back from its holder through a signed `revoke_assignment` plan. In the team tier the review queue never lists tasks the reviewer annotated, and an opened task that this person annotated in any round shows no approve or return controls; the server refuses such a review either way. MCP and agents can still only prepare these plans; signing and execution happen in the UI.

The UI hides actions outside effective scopes. All writes still use the existing controlled action routes and server ownership/role checks. Source reads use existing project/source grants. A zero-user instance retains local personal behavior.

## Lossless training round trips

`AnnotationRecord` adds optional polygons and record/shape/span attributes. Existing fields and endpoints remain compatible. Finalized records can be exported with controlled `export_dataset`, `format: "annotations_jsonl"`. The archive contains `annotations.jsonl` with full core records; import through the existing version training `import-annotations` endpoint using `format: "annotations_jsonl"`, `annotations_jsonl`, and a fresh `idempotency_key`. Standard COCO/YOLO behavior is unchanged; those detection formats do not represent every workbench component/property.

## Canvas choice

Konva and react-konva are the only added direct runtime dependencies, pinned to **10.9.0** and **19.3.2**. Their runtime dependency closure and shipped modules pass the existing license audit. The decision was fixed before implementation; the suitability assessments below are engineering judgments based on the linked upstream documentation.

License sources: [Konva](https://github.com/konvajs/konva/blob/master/LICENSE), [react-konva](https://github.com/konvajs/react-konva/blob/master/LICENSE), [Fabric.js](https://github.com/fabricjs/fabric.js/blob/master/LICENSE), [PixiJS](https://github.com/pixijs/pixijs/blob/dev/LICENSE).

| Option | Relevant upstream capabilities | Assessment for this workbench |
|---|---|---|
| [Konva](https://konvajs.org/docs/overview.html), [react-konva](https://github.com/konvajs/react-konva) | Canvas scene graph, hit detection, layers, shapes, transforms, React bindings; MIT | Chosen. Declarative shape editing fits the existing React state/history boundary. Native DOM controls supply keyboard accessibility. |
| [Fabric.js](https://www.fabricjs.com/docs/) | Interactive object canvas, controls, custom properties, serialization; MIT | Suitable object editing, but its independent canvas object state would need an additional React synchronization boundary. |
| [PixiJS](https://pixijs.com/8.x/guides/concepts/render-loop) | GPU scene rendering and continuous render-loop control; MIT | Attractive for dense animated scenes; annotation handles and form/accessibility behavior would require more custom work. |
| [Canvas2D](https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API) / [SVG](https://www.w3.org/TR/SVG2/) | Browser-native raster drawing / vector DOM | No library dependency, but hit testing, selection transforms and interaction synchronization would need to be maintained locally. SVG is useful for smaller DOM-based drawings. |

The Konva backing canvas stays at viewport size. Large images expose a 1024-pixel preview and then replace it with the decoded original. Zoom/pan transforms a group rather than allocating an 8000×6000 backing canvas. This is progressive image loading, not a tile server. Performance limits must be measured on the target browser/hardware.

## Reproducible checks

Generate local-only fixtures (including 2000×1500, 3840×2160, and 8000×6000 images):

```sh
DATAKEEL_HOME=/tmp/workbench-home uv run python scripts/workbench_fixture.py \
  --output /tmp/workbench-manifest.json --source-dir /tmp/workbench-source
DATAKEEL_HOME=/tmp/workbench-home uv run python scripts/workbench_fixture.py --serve
cd web
npm run smoke:workbench -- http://127.0.0.1:8840 /tmp/workbench-evidence /tmp/workbench-manifest.json
```

The runner measures W1–W5 against real APIs, checks keyboard-only annotation/submission, offline recovery and explicit conflict decisions, 200 undo/redo steps per component, and five seconds of large-image panning. It records metrics and light/dark screenshots. Use a fresh fixture for each full run. PostgreSQL fixtures use `--test-database --schema p30_workbench` with an explicitly authorized isolated test database supplied by the host; never use an unknown/shared database. API and Web use port 8840.

Rendering/state tests use Vitest. The standard type, lint, API, token, contrast, source-hash, build and license checks remain in place. A browser launch blocked by the host sandbox is an unmeasured result, not a performance pass. Full SQLite/PostgreSQL gates and full mutation runs remain integration CI responsibilities for this task.
