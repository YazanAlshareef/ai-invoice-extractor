import csv
from datetime import date
from pathlib import Path

from extractor.llm import ExtractionError, FixtureExtractor
from extractor.pipeline import run

ROOT = Path(__file__).resolve().parent.parent
TODAY = date(2026, 11, 6)


def rows(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def one_file_inbox(tmp_path):
    inbox = tmp_path / "in"
    inbox.mkdir()
    (inbox / "x.pdf").write_bytes(b"x")
    return inbox


def test_dry_run_on_synthetic_set(tmp_path):
    res = run(ROOT / "inbox", FixtureExtractor(ROOT / "fixtures"), tmp_path, TODAY)
    ok = sorted(k for k, (s, _) in res.items() if s == "ok")
    assert ok == ["inv_01.pdf", "inv_02.pdf", "inv_03.pdf", "inv_05.pdf", "inv_07.pdf", "inv_08.png"]
    review = {r["source_file"]: r["reason"] for r in rows(tmp_path / "review.csv")}
    assert set(review) == {"inv_04.png", "inv_06.pdf", "inv_09.pdf", "inv_10.pdf", "inv_11.pdf", "inv_12.png"}
    assert "duplicate" in review["inv_10.pdf"] and "future" in review["inv_11.pdf"]
    assert len(rows(tmp_path / "invoices.csv")) == 6


def test_rerun_writes_nothing_new(tmp_path):
    ex = FixtureExtractor(ROOT / "fixtures")
    run(ROOT / "inbox", ex, tmp_path, TODAY)
    res = run(ROOT / "inbox", ex, tmp_path, TODAY)
    assert sum(s == "ok" for s, _ in res.values()) == 0
    assert len(rows(tmp_path / "invoices.csv")) == 6


def test_extraction_failure_goes_to_review(tmp_path):
    class Broken:
        def extract(self, p):
            raise ExtractionError("rate limited")

    res = run(one_file_inbox(tmp_path), Broken(), tmp_path / "out", TODAY)
    assert res["x.pdf"][0] == "review"
    assert "rate limited" in rows(tmp_path / "out" / "review.csv")[0]["reason"]


def test_schema_failure_goes_to_review(tmp_path):
    class Bad:
        def extract(self, p):
            return {"vendor": "A"}

    run(one_file_inbox(tmp_path), Bad(), tmp_path / "out", TODAY)
    assert "schema" in rows(tmp_path / "out" / "review.csv")[0]["reason"]
