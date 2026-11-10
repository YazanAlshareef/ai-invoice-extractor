"""Pydantic models for one extracted invoice."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = Field(min_length=1)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)


class Invoice(BaseModel):
    vendor: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    invoice_date: date
    subtotal: Decimal = Field(ge=0)
    tax: Decimal = Field(ge=0)
    total: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    line_items: list[LineItem] = Field(min_length=1)
    # model's own 0..1 self-rating; used to route weak rows to review
    confidence: float = Field(default=1.0, ge=0, le=1)
