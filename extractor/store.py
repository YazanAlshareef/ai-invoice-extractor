"""Output: SQLite (source of truth, used for duplicate lookup) + CSV copies."""
import csv
import json
import sqlite3
from pathlib import Path

from .checks import dup_key
from .schema import Invoice

INV_COLS = ["source_file", "vendor", "invoice_number", "invoice_date", "subtotal", "tax", "total", "currency", "confidence"]
LINE_COLS = ["invoice_number", "vendor", "description", "quantity", "unit_price", "amount"]
REVIEW_COLS = ["source_file", "reason", "raw_json"]


def _append(path: Path, cols, row):
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        w.writerow(row)


class Store:
    def __init__(self, out_dir="out"):
        self.dir = Path(out_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.dir / "invoices.sqlite")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS invoices(
          dup_key TEXT PRIMARY KEY, file_hash TEXT, source_file TEXT, vendor TEXT, invoice_number TEXT,
          invoice_date TEXT, subtotal TEXT, tax TEXT, total TEXT, currency TEXT, confidence REAL);
        CREATE TABLE IF NOT EXISTS line_items(
          dup_key TEXT REFERENCES invoices(dup_key), description TEXT, quantity TEXT, unit_price TEXT, amount TEXT);
        """)

    def seen_hashes(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT file_hash FROM invoices")}

    def seen_keys(self) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT dup_key FROM invoices")}

    def add_invoice(self, inv: Invoice, source_file: str, file_hash: str = ""):
        k = dup_key(inv)
        row = {"source_file": source_file, **inv.model_dump(mode="json", exclude={"line_items"})}
        with self.db:
            self.db.execute("INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (k, file_hash, *[row[c] for c in INV_COLS]))
            self.db.executemany("INSERT INTO line_items VALUES(?,?,?,?,?)",
                                [(k, li.description, str(li.quantity), str(li.unit_price), str(li.amount)) for li in inv.line_items])
        _append(self.dir / "invoices.csv", INV_COLS, row)
        for li in inv.line_items:
            _append(self.dir / "line_items.csv", LINE_COLS,
                    {"invoice_number": inv.invoice_number, "vendor": inv.vendor, **li.model_dump(mode="json")})

    def add_review(self, source_file: str, reasons: list[str], raw):
        _append(self.dir / "review.csv", REVIEW_COLS,
                {"source_file": source_file, "reason": "; ".join(reasons), "raw_json": json.dumps(raw)})

    def close(self):
        self.db.close()
