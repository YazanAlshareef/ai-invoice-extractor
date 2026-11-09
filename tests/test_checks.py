from datetime import date
from decimal import Decimal

from extractor import checks
from extractor.schema import Invoice


def raw(**kw):
    base = {"vendor": "Acme", "invoice_number": "A1", "invoice_date": "2026-01-10", "subtotal": "30.00",
            "tax": "3.00", "total": "33.00", "currency": "USD", "confidence": 0.9,
            "line_items": [{"description": "x", "quantity": "2", "unit_price": "10.00", "amount": "20.00"},
                           {"description": "y", "quantity": "1", "unit_price": "10.00", "amount": "10.00"}]}
    base.update(kw)
    return base


def inv(**kw):
    i, errs = checks.validate(raw(**kw))
    assert errs == []
    return i


def test_valid_invoice_passes_everything():
    i = inv()
    assert checks.check_totals(i) == []
    assert checks.check_date(i, date(2026, 6, 1)) == []
    assert checks.check_confidence(i) == []


def test_schema_rejects_missing_and_negative_fields():
    i, errs = checks.validate(raw(vendor="", total="-1"))
    assert i is None and len(errs) == 2
    i, errs = checks.validate({"vendor": "A"})
    assert i is None and any("invoice_date" in e for e in errs)


def test_schema_rejects_bad_date_and_empty_lines():
    assert checks.validate(raw(invoice_date="10/01/2026"))[0] is None
    assert checks.validate(raw(line_items=[]))[0] is None


def test_totals_total_mismatch():
    assert any("!= total" in p for p in checks.check_totals(inv(total="40.00")))


def test_totals_line_sum_mismatch():
    assert any("!= subtotal" in p for p in checks.check_totals(inv(subtotal="31.00", total="34.00")))


def test_totals_line_math_mismatch():
    lines = raw()["line_items"]
    lines[0]["amount"] = "25.00"
    problems = checks.check_totals(inv(line_items=lines, subtotal="35.00", total="38.00"))
    assert any("line 1" in p for p in problems)


def test_totals_one_cent_rounding_tolerated():
    assert checks.check_totals(inv(total="33.01")) == []
    assert checks.check_totals(inv(total="33.02")) != []


def test_fractional_quantity():
    lines = [{"description": "z", "quantity": "1.5", "unit_price": "10.00", "amount": "15.00"}]
    assert checks.check_totals(inv(line_items=lines, subtotal="15.00", tax="0", total="15.00")) == []


def test_date_future_and_ancient():
    today = date(2026, 6, 1)
    assert checks.check_date(inv(invoice_date="2026-06-02"), today)
    assert checks.check_date(inv(invoice_date="2026-06-01"), today) == []
    assert checks.check_date(inv(invoice_date="2001-01-01"), today)


def test_duplicate_detection_ignores_case_and_spaces():
    seen = {checks.dup_key(inv())}
    assert checks.check_duplicate(inv(vendor=" ACME ", invoice_number="a1"), seen)
    assert checks.check_duplicate(inv(invoice_number="A2"), seen) == []
    assert checks.check_duplicate(inv(vendor="Other"), seen) == []


def test_low_confidence():
    assert checks.check_confidence(inv(confidence=0.5))
    assert checks.check_confidence(inv(confidence=0.8)) == []


def test_money_is_decimal_not_float():
    assert isinstance(inv(), Invoice) and isinstance(inv().total, Decimal)
