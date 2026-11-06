"""inbox file -> extractor -> validate -> checks -> store or review."""
from datetime import date
from pathlib import Path

from . import checks
from .llm import ExtractionError
from .store import Store

EXTS = {".pdf", ".png", ".jpg", ".jpeg"}


def process_file(path: Path, extractor, store: Store, seen: set[str], today: date | None = None):
    """Returns ("ok", []) or ("review", reasons)."""
    try:
        raw = extractor.extract(path)
    except ExtractionError as e:
        store.add_review(path.name, [f"extraction failed: {e}"], None)
        return "review", [str(e)]
    inv, problems = checks.validate(raw)
    if inv is not None:
        problems = (checks.check_totals(inv) + checks.check_date(inv, today)
                    + checks.check_duplicate(inv, seen) + checks.check_confidence(inv))
    if problems:
        store.add_review(path.name, problems, raw)
        return "review", problems
    store.add_invoice(inv, path.name)
    seen.add(checks.dup_key(inv))
    return "ok", []


def run(inbox, extractor, out_dir="out", today: date | None = None):
    store = Store(out_dir)
    seen = store.seen_keys()
    results = {}
    for p in sorted(Path(inbox).iterdir()):
        if p.suffix.lower() in EXTS:
            results[p.name] = process_file(p, extractor, store, seen, today)
    store.close()
    return results
