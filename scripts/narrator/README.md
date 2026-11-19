# Narrator

Narrator is a standalone Python tool for short labels and source-grounded
summaries. Supply a reasoning adapter as an absolute executable and its
arguments. The tool reads text from stdin.

## Generate a label

Send one UTF-8 text on stdin and set `--max-words` to a positive integer. The
same command works for a block, a message or the text of a Chat Session. It
accepts up to 192,000 input bytes. The label can be a single word or a fragment.

The budget counts words after ignoring case and surrounding punctuation.
Standalone punctuation and symbols use no budget. Hyphenated terms such as
`single-checkout` count as one word. The following words can appear without
using the budget: `a`, `an`, `and`, `and/or`, `as`, `at`, `but`, `by`, `for`,
`from`, `in`, `nor`, `of`, `on`, `or`, `so`, `the`, `to`, `with`, and `yet`.
For example, `Progress and background jobs` uses three counted words. Every
label needs at least one counted word.

```sh
printf '%s\n' 'A final summary may be as long as its source.' |
  /absolute/path/to/python3.13 /absolute/checkout/mycel/scripts/narrator/narrator.py \
    label --max-words 2 \
    --model-command '["/absolute/path/to/codex-adapter"]'
```

The model adapter receives the instructions and a JSON object with `text` and
`max_words`. Its response contains one `label` string, for example
`{"label":"Source Length"}`. The metered response form described below is also
supported. Narrator normalizes whitespace, validates the label against the word
limit and writes one newline-terminated line. If a reply fails validation,
Narrator asks once more. Failure leaves stdout empty and writes a diagnostic
to stderr.

## Summarize text

Supply up to 48,000 Unicode code points of UTF-8 text on stdin with
`--plain-text`. Narrator checks claims against the source, allows one bounded
repair and recheck, and returns whole verified units. The output cannot exceed
the input's character count.

```sh
python3 scripts/narrator/narrator.py --plain-text \
  --model-command '["/absolute/path/to/reasoning-adapter"]' < source.md
```

The packaged entry point is `python3 -m mycel._narrator.narrator`.
The standalone command also accepts previously framed requests with
`--source-characters`. A previous custom framing profile can still be selected
with `--instructions` for those requests.

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
`--report /absolute/private/path/new-receipt.json`. Supply the same source text on stdin with `--plain-text`. The receipt is created exclusively with owner-only
permissions before any model launch. Keep it outside source control and
indexes since it contains source excerpts, model proposals, and final prose.

Compare mode uses one extraction and gives each arm the same remaining
time and text allowance. Only the semantic arm spends the embedding call.
The pair can launch at most 14 text commands and one embedding command.
It emits empty stdout. If either arm fails, it exits nonzero and keeps any
completed arm and the failure in the receipt.

Direct `reasoned` or `semantic` runs can also provide a new `--report` path.
For existing framed requests, pass `--source-characters N` with the sum of the
original section bodies' Unicode code point counts. Count the original text before
framing is added or an oversized input is cut.

The receipt records the request digest and exact admitted passages,
extraction outcomes, per-arm starting allowance and events, supported and
repaired revisions, Selection and budget dispositions, prose and physical
launch totals. Each completed arm reports source and summary character counts
and the summary-to-source ratio. The receipt hashes the adapter argv.

## Compare writer revisions

Pin the source, interpreter, exact case bytes, model adapters and scoring
rubric. Run each revision on the same input, count failures, and keep the
private receipts for coverage and evidence review.
