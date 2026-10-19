"""Plain data classes and money helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation


def to_decimal(value: object) -> Decimal:
    """Parse API/sheet numbers: 1290, 1290.5, "1290.0000", "1 290,50". Raises ValueError."""
    if value is None or isinstance(value, bool):
        raise ValueError(f"not a number: {value!r}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, float)):
        result = Decimal(str(value))
    else:
        text = str(value).strip().replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            result = Decimal(text)
        except InvalidOperation:
            raise ValueError(f"not a number: {value!r}") from None
    if not result.is_finite():
        raise ValueError(f"not a finite number: {value!r}")
    return result


def fmt_price(value: Decimal) -> str:
    """The string Ozon expects: whole numbers without a fraction, otherwise two digits."""
    if value == value.to_integral_value():
        return str(int(value))
    return f"{value:.2f}"


@dataclass
class Product:
    offer_id: str
    product_id: int
    name: str = ""
    price: Decimal = Decimal(0)
    old_price: Decimal = Decimal(0)
    min_price: Decimal = Decimal(0)
    currency: str = "RUB"
    fbs_present: int = 0
    fbs_reserved: int = 0
    fbo_present: int = 0


@dataclass
class PostingLine:
    offer_id: str
    sku: int | None
    name: str
    quantity: int
    price: Decimal
    currency: str


@dataclass
class Posting:
    posting_number: str
    order_number: str
    status: str
    in_process_at: datetime  # timezone-aware, UTC
    shipment_date: datetime | None
    delivery_method: str
    city: str
    lines: list[PostingLine] = field(default_factory=list)


@dataclass
class ItemResult:
    offer_id: str
    ok: bool
    errors: list[str] = field(default_factory=list)
