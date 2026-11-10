"""Field-level accuracy of an extractor against truth/*.json.

python -m extractor.evaluate --dry-run     (scores the hand-made fixtures, NOT a model)
python -m extractor.evaluate               (scores the live model; needs a key)
"""
import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

from .llm import ExtractionError, FatalExtractionError, get_extractor

FIELDS = ["vendor", "invoice_number", "invoice_date", "subtotal", "tax", "total"]


def same(a, b):
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return str(a).strip() == str(b).strip()


def score(raw: dict, truth: dict) -> dict:
    out = {f: same(raw.get(f), truth[f]) for f in FIELDS}
    rl, tl = raw.get("line_items") or [], truth["line_items"]
    out["line_items"] = len(rl) == len(tl) and all(
        same(a.get("description"), b["description"]) and same(a.get("quantity"), b["quantity"])
        and same(a.get("unit_price"), b["unit_price"]) and same(a.get("amount"), b["amount"])
        for a, b in zip(rl, tl))
    return out


def evaluate(extractor, inbox="inbox", truth_dir="truth"):
    rows = {}
    for t in sorted(Path(truth_dir).glob("*.json")):
        f = next(Path(inbox).glob(t.stem + ".*"), None)
        if f is None:
            raise SystemExit(f"no file in {inbox}/ for truth/{t.name}")
        truth = json.loads(t.read_text(encoding="utf-8"))
        try:
            rows[t.stem] = score(extractor.extract(f), truth)
        except FatalExtractionError:
            raise  # same failure for every file: stop instead of reporting 0%
        except ExtractionError as e:
            rows[t.stem] = {k: False for k in FIELDS + ["line_items"]}
            print(f"{t.stem}: extraction failed: {e}")
    return rows


def report(rows):
    cols = FIELDS + ["line_items"]
    n = len(rows)
    lines = [f"{'field':16} correct"]
    for c in cols:
        k = sum(r[c] for r in rows.values())
        lines.append(f"{c:16} {k}/{n} ({100 * k / n:.0f}%)")
    tot = sum(r[c] for r in rows.values() for c in cols)
    lines.append(f"{'ALL FIELDS':16} {tot}/{n * len(cols)} ({100 * tot / (n * len(cols)):.0f}%)")
    for s, r in rows.items():
        bad = [c for c in cols if not r[c]]
        if bad:
            lines.append(f"  wrong in {s}: {', '.join(bad)}")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    load_dotenv(".env.local")
    try:
        print(report(evaluate(get_extractor(a.dry_run))))
    except ExtractionError as e:  # includes FatalExtractionError (bad key, retired model)
        raise SystemExit(f"evaluation stopped: {e}")
