"""inbox file -> extractor -> validate -> checks -> store or review."""
import hashlib
from datetime import date
from pathlib import Path

from . import checks
from .llm import ExtractionError, FatalExtractionError
from .store import Store

EXTS = {".pdf", ".png", ".jpg", ".jpeg"}


def process_file(path: Path, extractor, store: Store, seen: set[str], today: date | None = None,
                 hashes: set[str] | None = None):
    """Returns ("ok", []), ("review", reasons) or ("skipped", [])."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if hashes is not None and digest in hashes:
        return "skipped", ["already stored"]
    try:
        raw = extractor.extract(path)
    except FatalExtractionError:
        raise
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
    store.add_invoice(inv, path.name, digest)
    seen.add(checks.dup_key(inv))
    return "ok", []


def run(inbox, extractor, out_dir="out", today: date | None = None):
    store = Store(out_dir)
    seen, hashes = store.seen_keys(), store.seen_hashes()
    results = {}
    for p in sorted(Path(inbox).iterdir()):
        if p.suffix.lower() in EXTS:
            results[p.name] = process_file(p, extractor, store, seen, today, hashes)
    store.close()
    return results
