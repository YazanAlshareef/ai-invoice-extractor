# Walkthrough: every file in plain English

Flow: a file lands in `inbox/` -> `llm.py` asks a model (or a cached fixture) for JSON -> `schema.py` checks the shape -> `checks.py` checks the numbers -> `store.py` writes good rows or sends bad ones to `review.csv`. Files already stored (same hash) are skipped on a re-run.

## `extractor/`

- **`schema.py`** Two Pydantic models, `Invoice` and `LineItem`. Money is `Decimal`, not float, so 0.1 + 0.2 is exactly 0.3. Pydantic rejects a missing vendor, a bad date, a negative total or an empty line list.
- **`llm.py`** The only file that knows about a provider.
  - `GeminiExtractor` sends the PDF/image bytes plus a prompt and asks for JSON. It retries on 429/5xx with growing waits (and uses the server's "retry in N s" hint when given). It also waits 6 s between calls to stay under the free-tier request limit.
  - Errors like a bad key or retired model (401/403/404) raise `FatalExtractionError` and stop the run, because every file would fail the same way. A 400 only sends that one file to review. Files over 15 MB are rejected before upload, and retry waits are capped at 60 s.
  - `FixtureExtractor` is `--dry-run`: it reads `fixtures/<name>.json` instead of calling anything.
  - `get_extractor` picks one using `--dry-run` or `LLM_PROVIDER`.
- **`checks.py`** The sanity checks, each returns a list of problems: line math (qty x price = amount), line sum = subtotal, subtotal + tax = total (1 cent tolerance), date not in the future and not before 2015, duplicate (same vendor + invoice number, case-insensitive), and confidence below 0.8.
- **`store.py`** Writes SQLite (`out/invoices.sqlite`, with a primary key on the duplicate key) and CSVs (`invoices.csv`, `line_items.csv`, `review.csv`). SQLite remembers invoices and file hashes between runs, so re-running the inbox does not double-count.
- **`pipeline.py`** `process_file` runs one file through extract -> validate -> checks -> store or review. `run` loops over the inbox.
- **`__main__.py`** The command line: `python -m extractor [--dry-run]`. Loads `.env.local`.
- **`synth.py`** Makes the 12 fake invoices, their ground truth, and the simulated model answers. Seeded, so output is repeatable.
- **`evaluate.py`** Compares extractor output with `truth/` field by field and prints accuracy.

## Project files

- **`requirements.txt`** Runtime packages: pydantic, google-genai, python-dotenv.
- **`requirements-dev.txt`** Adds pytest, reportlab and pillow (for tests and the synthetic generator).
- **`.env.example`** Template for `.env.local`: provider, model name, empty key slot. Copy it; never put a real key in it.
- **`.gitignore`** Keeps `.env.local`, `out/`, databases and caches out of git.
- **`LICENSE`** MIT.
- **`extractor/__init__.py`** Empty; makes `extractor` a package so `python -m extractor` works.

## Data folders

- **`inbox/`** 12 synthetic invoices (9 PDF, 3 PNG). All say "SYNTHETIC SAMPLE".
- **`truth/`** What is actually printed on each invoice. 10, 11 and 12 are planted problems (duplicate of 01, year-2099 date, printed total wrong by 10.00).
- **`fixtures/`** Hand-written stand-ins for model answers. Four contain deliberate mistakes (see README). They are not real Gemini output.

## `tests/`

- **`test_checks.py`** Validators, totals, dates, duplicates, confidence.
- **`test_llm.py`** The adapter with a fake client: retry, backoff, server delay, giving up, fatal errors, bad JSON, 6 s spacing, missing key.
- **`test_pipeline.py`** Whole pipeline on the synthetic set, re-run safety, failures going to review.

## Likely interview questions

- *Why Decimal?* Float rounding breaks "do totals add up".
- *Why not trust the model's confidence alone?* It is self-reported. The arithmetic checks are independent and caught most of the injected errors.
- *What do the checks miss?* A consistently wrong value, e.g. a misspelled vendor (inv_08), passes every check. Only a human or a ground-truth comparison finds it.
- *Why a fixture mode?* Tests and CI need no key, no network, no quota.
