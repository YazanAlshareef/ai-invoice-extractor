# AI Invoice Extractor

Drop invoice PDFs/images in `inbox/`. A model (Gemini) reads each one and returns JSON: vendor, date, total, tax, line items. The pipeline validates it with Pydantic, runs sanity checks (totals add up, date plausible, no duplicates), and writes good rows to SQLite + CSV. Anything doubtful goes to `review.csv` with the reason.

**All sample invoices are synthetic** (made by `extractor/synth.py`, stamped "SYNTHETIC SAMPLE"). No real documents are used.

## Status: live Gemini run NOT completed

- **Verified offline:** 27 pytest tests pass with no key and no network. `--dry-run` works end to end.
- **Not verified:** accuracy of real Gemini output. The live run did not complete. On the last attempt even a plain text "say ok" call returned `503`/`504` (`DEADLINE_EXCEEDED`) from the service, so I could not tell whether the model reads these invoices well. Treat the adapter as tested against a fake client only.
- The accuracy table below measures **hand-made fixtures** (stand-ins for model output with deliberate mistakes). It tests the checks and the scoring, not Gemini.

## How to run

```bash
pip install -r requirements-dev.txt
python -m pytest                     # offline, no key
python -m extractor --dry-run        # uses fixtures/, no key
python -m extractor.evaluate --dry-run   # field accuracy vs truth/
python -m extractor.synth            # regenerate the synthetic set
```

Live (needs a key): copy `.env.example` to `.env.local`, fill in `GEMINI_API_KEY`, optionally set `GEMINI_MODEL`, then `python -m extractor`. Output goes to `out/`: `invoices.sqlite`, `invoices.csv`, `line_items.csv`, `review.csv`.

## Dry-run results (fixtures, not Gemini)

12 synthetic invoices, 6 written, 6 sent to review:

| file | why it went to review |
|---|---|
| inv_04 | subtotal + tax != total (fixture misreads total) |
| inv_06 | line items sum != subtotal (fixture drops a line) |
| inv_09 | confidence 0.55 |
| inv_10 | duplicate of inv_01 (planted) |
| inv_11 | date 2099-01-01 (planted) |
| inv_12 | printed total wrong by 10.00 (planted) |

Field accuracy of the fixtures against the truth: 81/84 (96%). Wrong: inv_04 total, inv_06 line items, inv_08 vendor. The fixtures were written from `truth/` with three mistakes added on purpose, so this figure only exercises `score()` and the checks. It says nothing about model accuracy.

**Limit this exposed:** inv_08 has a vendor typo (`o` for `0`). It is self-consistent, so it passes every check and lands in `invoices.csv` wrong. Arithmetic checks cannot catch a consistently wrong value.

## How an AI coding assistant helped

An AI coding assistant wrote most of the first draft: schema, adapter, checks, tests, synthetic generator. I specified the checks and the review flow. Everything was run, and the test and dry-run output above is real output.

## What broke and how it got fixed

- **Wrong model name:** my first live attempt got `404` (model retired for new users). Every file then flooded `review.csv` with the same error. Fix: errors 401/403/404 now raise `FatalExtractionError` and stop the run (a 400 only sends that one file to review); test added.
- **Default model is unverified:** the default in `GEMINI_MODEL` / `llm.py` has never worked in a live call here. Set `GEMINI_MODEL` to a model your key can use.
- **Missing key:** now fails at start with a clear message instead of per file.
- **Hanging call:** one live call ran ~20 minutes. Added a 60 s request timeout and treat client timeouts as retryable (504).
- **Still broken:** the service keeps returning 503/504, see Status.

## Design notes

- Money is `Decimal`, not float.
- `llm.py` is the only provider-specific file. Model name comes from `GEMINI_MODEL`; `LLM_PROVIDER` selects the provider.
- Retries: 429/500/502/503/504 with exponential backoff + jitter, honoring the server's retry delay. 6 s minimum gap between calls for free-tier limits.
- Re-running the inbox does not double-count: files already stored (same SHA-256) are skipped, and the SQLite primary key on vendor + invoice number backs that up. Files that went to review are tried again on every run, so `review.csv` can hold the same file more than once. An `out/` folder from an older version has a different table layout: delete it.
- Prompt asks the model for the printed currency and says text inside a document is data, not instructions. Files over 15 MB are sent to review without a call. Retry waits are capped at 60 s.

## Limits

- Live accuracy unknown (see Status).
- Duplicate key is vendor + invoice number; a misread vendor evades it.
- One currency per invoice, no multi-page handling beyond what the model does.
- Confidence is self-reported by the model.

See `WALKTHROUGH.md` for a file-by-file explanation. MIT licensed.
