import argparse
import sys

from dotenv import load_dotenv

from .llm import ExtractionError, get_extractor
from .pipeline import run


def main(argv=None):
    ap = argparse.ArgumentParser(prog="extractor", description="Invoices in /inbox -> CSV/SQLite, bad rows -> review.csv")
    ap.add_argument("--inbox", default="inbox")
    ap.add_argument("--out", default="out")
    ap.add_argument("--fixtures", default="fixtures")
    ap.add_argument("--dry-run", action="store_true", help="use cached fixture responses, no API key needed")
    a = ap.parse_args(argv)
    load_dotenv(".env.local")
    try:
        results = run(a.inbox, get_extractor(a.dry_run, a.fixtures), a.out)
    except ExtractionError as e:
        sys.exit(f"error: {e}")
    for name, (status, reasons) in results.items():
        print(f"{status:7} {name}" + (f"  <- {'; '.join(reasons)}" if reasons else ""))
    ok = sum(s == "ok" for s, _ in results.values())
    print(f"\n{ok} written, {len(results) - ok} sent to review ({a.out}/review.csv)")


if __name__ == "__main__":
    main()
