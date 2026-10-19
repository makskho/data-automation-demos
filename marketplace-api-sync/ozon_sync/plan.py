"""Validate the seller's sheet against the live catalogue and build the change plan (the diff)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from .client import PriceUpdate, StockUpdate
from .models import Product, fmt_price
from .sheets import SheetRow

BIG_CHANGE_RATIO = Decimal("0.5")

FIELD_LABEL = {
    "price": "Цена",
    "old_price": "Цена до скидки",
    "min_price": "Минимальная цена",
    "fbs_present": "Остаток FBS",
}


@dataclass(frozen=True)
class Issue:
    row_no: int
    offer_id: str
    code: str
    message: str


@dataclass(frozen=True)
class Change:
    offer_id: str
    field: str
    old: Decimal | int
    new: Decimal | int
    warning: str = ""


@dataclass
class Plan:
    changes: list[Change] = field(default_factory=list)
    price_updates: list[PriceUpdate] = field(default_factory=list)
    stock_updates: list[StockUpdate] = field(default_factory=list)
    unchanged_rows: int = 0

    @property
    def warnings(self) -> list[Change]:
        return [c for c in self.changes if c.warning]


def validate(rows: Sequence[SheetRow], catalog: Sequence[Product]) -> tuple[list[SheetRow], list[Issue]]:
    """Split rows into (valid, issues). A row with any problem is excluded as a whole."""
    by_offer = {p.offer_id: p for p in catalog}
    seen: dict[str, list[int]] = {}
    for row in rows:
        if row.offer_id:
            seen.setdefault(row.offer_id, []).append(row.row_no)

    valid: list[SheetRow] = []
    issues: list[Issue] = []
    for row in rows:
        problems: list[tuple[str, str]] = list(row.parse_errors)
        if not row.offer_id:
            problems.append(("empty_sku", "пустой артикул"))
        else:
            if len(seen[row.offer_id]) > 1:
                problems.append(("duplicate", f"артикул повторяется в строках {', '.join(map(str, seen[row.offer_id]))}"))
            if row.offer_id not in by_offer:
                problems.append(("unknown_sku", "артикул не найден в каталоге Ozon"))
        if row.fbs_present is not None and row.fbs_present < 0:
            problems.append(("negative_stock", f"отрицательный остаток: {row.fbs_present}"))
        for key in ("price", "min_price", "old_price"):
            value = getattr(row, key)
            if value is None:
                continue
            if value < 0:
                problems.append(("negative_price", f"{FIELD_LABEL[key]}: отрицательное значение {value}"))
            elif key == "price" and value == 0:
                problems.append(("price_not_positive", "цена должна быть больше 0"))

        product = by_offer.get(row.offer_id)
        if product is not None and not any(code in ("bad_number", "negative_price", "price_not_positive") for code, _ in problems):
            price = row.price if row.price is not None else product.price
            old = row.old_price if row.old_price is not None else product.old_price
            minimum = row.min_price if row.min_price is not None else product.min_price
            if old != 0 and old <= price and (row.price is not None or row.old_price is not None):
                problems.append(("old_price_below_price", f"цена до скидки ({fmt_price(old)}) должна быть больше цены ({fmt_price(price)}) или 0"))
            if minimum > price and (row.price is not None or row.min_price is not None):
                problems.append(("min_price_above_price", f"минимальная цена ({fmt_price(minimum)}) выше цены ({fmt_price(price)})"))

        if problems:
            issues.extend(Issue(row.row_no, row.offer_id, code, text) for code, text in problems)
        else:
            valid.append(row)
    return valid, issues


def build_plan(rows: Sequence[SheetRow], catalog: Sequence[Product]) -> Plan:
    """Compare valid rows with the live values. Only differences become changes."""
    by_offer = {p.offer_id: p for p in catalog}
    plan = Plan()
    for row in rows:
        product = by_offer[row.offer_id]
        row_changed = False

        new_price = row.price if row.price is not None else product.price
        new_old = row.old_price if row.old_price is not None else product.old_price
        new_min = row.min_price if row.min_price is not None else product.min_price
        price_changed = False
        for key, new, old in (("price", new_price, product.price), ("old_price", new_old, product.old_price), ("min_price", new_min, product.min_price)):
            if new != old:
                price_changed = True
                warning = ""
                if key == "price" and old > 0 and abs(new - old) / old > BIG_CHANGE_RATIO:
                    warning = f"изменение больше {int(BIG_CHANGE_RATIO * 100)}%"
                plan.changes.append(Change(row.offer_id, key, old, new, warning))
        if price_changed:
            plan.price_updates.append(PriceUpdate(row.offer_id, new_price, new_old, new_min, product.currency))
            row_changed = True

        if row.fbs_present is not None and row.fbs_present != product.fbs_present:
            plan.changes.append(Change(row.offer_id, "fbs_present", product.fbs_present, row.fbs_present))
            plan.stock_updates.append(StockUpdate(row.offer_id, product.product_id, row.fbs_present))
            row_changed = True

        if not row_changed:
            plan.unchanged_rows += 1
    return plan


# ---- text output ------------------------------------------------------------------------------


def render_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    cells = [[str(c) for c in row] for row in rows]
    widths = [max([len(h)] + [len(r[i]) for r in cells]) for i, h in enumerate(headers)]

    def line(values: Sequence[str]) -> str:
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(values)).rstrip()

    return "\n".join([line(list(headers)), line(["-" * w for w in widths])] + [line(r) for r in cells])


def _show(value: Decimal | int) -> str:
    return fmt_price(value) if isinstance(value, Decimal) else str(value)


def render_diff(plan: Plan) -> str:
    if not plan.changes:
        return "Изменений нет: таблица совпадает с данными Ozon."
    rows = [
        (c.offer_id, FIELD_LABEL[c.field], _show(c.old), "->", _show(c.new), ("! " + c.warning) if c.warning else "")
        for c in plan.changes
    ]
    return render_table(["Артикул", "Поле", "Сейчас", "", "Станет", "Внимание"], rows)


def render_issues(issues: Sequence[Issue]) -> str:
    return render_table(["Строка", "Артикул", "Код", "Проблема"], [(i.row_no, i.offer_id, i.code, i.message) for i in issues])
