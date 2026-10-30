# One sentence to plan

[中文](ONE_SENTENCE.zh.md)

Type what you want in the Agent dialog, for example "Set up a box annotation project for car and truck with two people cross-checking and a 10% spot check". Datakeel turns the sentence into a chain of existing controlled actions, shows what each step changes, what it costs and whether it needs a signature, and runs nothing until you confirm. Questions such as "who has the highest rework rate" are answered directly by a read function.

## How a sentence is understood

1. **Rules first.** A few fixed recipes (set up an annotation project, take back someone's untouched tasks and give them to someone else, draft a label set) and simple read questions are recognised without a model.
2. **Then one model call.** Otherwise one bounded call is made to the conversation's model. The prompt contains the registry (every action and read function with its Chinese and English wording), the schemas of the likely candidates, the visible objects (people, projects, datasets, versions, label sets) and the page context. The answer must be one JSON object; anything else is discarded.
3. **Strict checking.** Every step must be a registered action with valid parameters. Names are resolved against the catalog: one match is used, several become a choice, none becomes a question. A project, package, dataset or label set used by a write must come from the page, the previous turn, an earlier step or the person's own words; a value the model copied from the catalog is turned back into a question. Only reads may fall back to the single existing project.

Parameters come from the sentence, the page context (dataset, version, project, package, task, label set and selection that the dialog sends) and the previous turn's objects. A missing required value is asked for; candidates can be picked with one click. A request the person may not perform is refused while planning, naming the missing scope (for example `production:manage`), exactly as the same action would be refused by hand.

The Web Agent dialog enters the planner for every message (it always sends page context). The HTTP message API enters it only when the request carries `context`, so older clients keep the free conversation.

## Chains, confirmation and resuming

A plan is stored as an action chain. Each step is an ordinary controlled action; `{"$ref": "s1.label_set_id"}` takes a value from an earlier step's receipt and a step may fan out over several targets.

- **Confirm**: the person presses **Confirm and run** (or runs `datakeel intents run <chain>`; HTTP `POST /api/intents/chains/{id}/run`). Steps are prepared and executed one by one through the same services as manual actions, so receipts, audit and lineage are identical and name the person.
- **Signatures**: a step that is irreversible, external or governed waits in the approval queue. Sign it in the chain card or on the Approvals page, then the chain continues.
- **Failure**: the chain stops at the failed step with its reason; finished steps stay done. **Resume** (or the same CLI/HTTP call) skips steps and fan-out targets that already executed and never repeats them.
- Only the person who asked can read or run a chain. MCP and the Agent can never confirm or execute a write: there is no MCP tool for chains, and the Agent only proposes.

`datakeel intents plan "<sentence>" [--dataset --version --project --package --actor]` plans from the command line; `datakeel intents show <chain>` prints it.

## Wording registry (required for every action)

The entry reads only the action registry. Every action and every read function must register Chinese and English phrases and at least two examples, one Chinese and one English. A gate test (`tests/intents/test_language_gate.py`) fails when an entry is missing any of them. Add wording for a new action as one 4-tuple in `datakeel/actions/action_language.py` (`ACTION_LANGUAGE`) or `datakeel/actions/production_language.py` (`PRODUCTION_LANGUAGE`): `(phrase_zh, phrase_en, example_zh, example_en)`. Read functions use `datakeel/ontology/function_language.py`.

## Drafting a label set and guidelines

`draft_label_set` is a controlled action ("Draft a vehicle label set and guidelines from these images"). It needs a signature and writes nothing before that. It reads:

- **Data standards**: a field's code list becomes the label tree; other standard fields become label attributes.
- **Existing annotations**: categories in annotation batches of the dataset and in earlier label sets.
- **Sampled files**: up to 50 files of the dataset version.

The result is a new **unpublished** label set version with Chinese and English names, attributes, an overview and per-label guidelines with positive and negative examples. Examples cite real sample ids; any id the model invents is dropped and counted. The version records its sources (standards, label sets, datasets, samples, model, tokens, cost, plan id). In the chain card, edit names and guidelines and **Save edits** (a `create_label_set` update plan), then **Publish…** through the ordinary `publish_label_set` signature sheet.

Profiles: `offline` (default, deterministic, no cost); `cloud-text` (`deepseek-flash`, key in `DATAKEEL_DRAFT_TEXT_API_KEY`); `cloud-vision` (`qwen3.5-flash` on DashScope with thumbnails, key in `DATAKEEL_DRAFT_VISION_API_KEY`). A cloud draft shows its estimated cost on the signature sheet and refuses to run when the approved `max_cost_usd` is below the estimate. Models and endpoints can be changed with `DATAKEEL_DRAFT_TEXT_MODEL`/`_BASE_URL` and `DATAKEEL_DRAFT_VISION_MODEL`/`_BASE_URL`.

## Limits

- Tasks cannot be selected by position ("the first two tasks"); the entry asks which tasks.
- `rework_rate` counts every review of the project; "this week" is not filtered and the answer says so.
- The planner model is the conversation's model. The offline demo provider uses only the recipes.
