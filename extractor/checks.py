"""Validation and sanity checks. Each check returns a list of problem strings."""
from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from .schema import Invoice

TOL = Decimal("0.01")
MIN_DATE = date(2015, 1, 1)
LOW_CONFIDENCE = 0.8


def validate(raw: dict) -> tuple[Invoice | None, list[str]]:
    try:
        return Invoice.model_validate(raw), []
    except ValidationError as e:
        return None, [f"schema: {err['loc']} {err['msg']}" for err in e.errors()]


def check_totals(inv: Invoice) -> list[str]:
    bad = []
    for i, li in enumerate(inv.line_items, 1):
        if abs(li.quantity * li.unit_price - li.amount) > TOL:
            bad.append(f"line {i}: qty*price {li.quantity * li.unit_price} != amount {li.amount}")
    lines = sum(li.amount for li in inv.line_items)
    if abs(lines - inv.subtotal) > TOL:
        bad.append(f"line items sum {lines} != subtotal {inv.subtotal}")
    if abs(inv.subtotal + inv.tax - inv.total) > TOL:
        bad.append(f"subtotal+tax {inv.subtotal + inv.tax} != total {inv.total}")
    return bad


def check_date(inv: Invoice, today: date | None = None) -> list[str]:
    today = today or date.today()
    if inv.invoice_date > today:
        return [f"date {inv.invoice_date} is in the future"]
    if inv.invoice_date < MIN_DATE:
        return [f"date {inv.invoice_date} is before {MIN_DATE}"]
    return []


def dup_key(inv: Invoice) -> str:
    return f"{inv.vendor.strip().lower()}|{inv.invoice_number.strip().lower()}"


def check_duplicate(inv: Invoice, seen: set[str]) -> list[str]:
    return [f"duplicate of vendor+number {inv.vendor} {inv.invoice_number}"] if dup_key(inv) in seen else []


def check_confidence(inv: Invoice, threshold: float = LOW_CONFIDENCE) -> list[str]:
    return [f"low confidence {inv.confidence}"] if inv.confidence < threshold else []
