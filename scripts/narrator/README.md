# Narrator summary writer

Narrator is an optional Mycel command that reads one complete MYC-8 summary
request from stdin. It extracts claims with exact citations, checks proposed
units independently, gives eligible rejections one repair and recheck, and
assembles whole supported units up to the original source length. The default
mode is `reasoned`. Length is measured in Unicode code points, including the
newlines between summary units. Any amount of compression is valid, including
an output of the same length as the source.

## Configure a disposable Mycel run

Use Python 3.13 or later and an absolute path to `narrator.py` in a Mycel
checkout. Keep `selection.py`, `verification.py` and the checkout’s packaged
prompt resource at the same source revision. Add the command to the
`[summaries]` section of the disposable settings file.

```toml
[summaries]
command = [
  "/absolute/path/to/python3.13",
  "/absolute/checkout/mycel/scripts/narrator/narrator.py",
  "--model-command",
  '["/absolute/path/to/reasoning-adapter", "--model", "pinned-model"]',
]
```

Set `MYCEL_CONFIG` to that disposable file and run a numbered Mycel Build
that supplies `MYCEL_SUMMARY_SOURCE_CHARACTERS` to the writer. The count comes
from the original section bodies, before adding generated place lines and
separators or cutting an oversized request. The repository's store, source
folders and embeddings come from its configuration.

```sh
MYCEL_CONFIG=/absolute/private/path/mycel.toml \
  /absolute/path/to/mycel -v "$MYCEL_BUILD" summaries build --repo fixture
```

Mycel launches the command with an empty working directory and a reduced
environment. Narrator emits only the exact verified UTF-8 prose on success.
A refusal exits nonzero with a short diagnostic on stderr and empty stdout.
Mycel can retry the whole command once and owns summary publication.

The default framing is the checkout's
[packaged prompt profile](../../src/mycel/data/summary-prompts.json). For a
Mycel `summaries.instructions` override, pass the same absolute directory as
`--instructions` to Narrator. It reads `raptor-summary.md` and
`raptor-request.md.tmpl` and matches their exact rendered framing before
launching a model command.

## Model and embedding commands

Use literal JSON argv arrays beginning with an absolute executable. Narrator
launches each adapter with complete stdin, bounded output, a new working
directory, and a reduced environment. The reasoning adapter receives a UTF-8
stage prompt followed by JSON data. It returns the requested JSON value or one
JSON fence. A metered adapter can use the `response` and `usage` envelope.

```json
{"response": [{"unit_id": "U1", "revision": 1, "verdict": "supported", "evidence_passage_ids": ["P001"]}], "usage": {"input_tokens": 450, "output_tokens": 30}}
```

Usage values are nonnegative integers under `input_tokens`,
`output_tokens`, or `total_tokens`. A plain reply or `null` usage leaves
provider token usage unavailable. Use an adapter that makes at most one
provider request per launch for qualification, so launch counts can be
reconciled with provider usage.

For `--mode semantic`, supply `--embedding-command` as JSON argv as well.
It receives an array of candidate claim strings in extraction order and
returns one finite, nonzero vector of equal dimension per claim, directly or
in the metered envelope. Narrator can make one embedding launch and uses its
cosine neighbors as pairs for Selection to compare.

The optional `voyage_embeddings.py` adapter takes `--model` and a literal
absolute `--key-command` JSON argv. The credential command receives empty
stdin and returns one token on stdout. The adapter reads that token privately
and performs a single HTTPS request. Use a credential command available in
Mycel's reduced child environment. [Voyage embeddings API](https://docs.voyageai.com/reference/embeddings-api)

The internal attempt deadline is 270 seconds. It allows up to eight text
launches, including one possible format retry each for extraction,
consolidation and initial verification and one launch each for repair and
fresh verification. The optional repair uses that same deadline and meter.
Without a supported repair, the original supported units remain eligible.

## Compare and retain evidence

Use `--mode compare` in a direct invocation with both adapter commands and
`--report /absolute/private/path/new-receipt.json`. Supply the same original
Mycel request on stdin. The receipt is created exclusively with owner-only
permissions before any model launch. Keep it outside source control and
indexes since it contains source excerpts, model proposals, and final prose.

Compare mode uses one extraction and gives each arm the same remaining
time and text allowance. Only the semantic arm spends the embedding call.
The pair can launch at most 14 text commands and one embedding command.
It emits empty stdout. If either arm fails, it exits nonzero and keeps any
completed arm and the failure in the receipt.

Direct `reasoned` or `semantic` runs can also provide a new `--report` path.
For any direct run, pass `--source-characters N` with the sum of the original
section bodies' Unicode code point counts. Count the original text before
Mycel adds framing or cuts an oversized input. The direct writer still emits
the same prose on success. Leave `--source-characters` and `--report` out of
the Mycel command for ordinary generation.

The receipt records the request digest and exact admitted passages,
extraction outcomes, per-arm starting allowance and events, supported and
repaired revisions, Selection and budget dispositions, prose and physical
launch totals. Each completed arm reports source and summary character counts
and the summary-to-source ratio. The receipt hashes the adapter argv.

## Qualify a pinned candidate

Record the exact source revision and file digests for the writer, Selection,
Verification and any adapters. Pin interpreter path and version, Mycel Build
and numerical dependencies, the prompt bytes, literal adapter argv and model
settings, the original source character count for each input, and the disposable
Mycel configuration. Retain
provider-free command-check results separately from live results.

The live qualification manifest also pins provider dispositions, the total
allowance, the case and rubric hashes, and the disposable retrieval fixture.
Run the pinned comparison and the actual two-level build and retrieval
checks before assessing the candidate for routine use.
