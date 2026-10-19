"""Ozon Seller API client: pagination, batching and response parsing on top of a Transport.

Endpoints (see README for the dates read and the verification note):
  POST /v3/product/list            product ids, cursor `last_id`
  POST /v3/product/info/list       names by offer_id
  POST /v5/product/info/prices     current prices, cursor `cursor`
  POST /v4/product/info/stocks     current stocks, cursor `cursor`
  POST /v2/products/stocks         set stock for a warehouse (<= 100 per request)
  POST /v1/product/import/prices   set prices (<= 1000 per request)
  POST /v3/posting/fbs/list        FBS postings, `offset` + `has_next`
  POST /v1/warehouse/list          seller warehouses
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator, Sequence

from .errors import ApiError
from .models import ItemResult, Posting, PostingLine, Product, fmt_price, to_decimal
from .transport import Transport

# Documented per-request limits. They are constants so tests can prove the batching respects them.
PRODUCT_LIST_LIMIT = 1000
INFO_BATCH = 1000  # offer_id values per info/prices/stocks request
STOCK_UPDATE_BATCH = 100
PRICE_UPDATE_BATCH = 1000
POSTING_PAGE = 100


@dataclass(frozen=True)
class PriceUpdate:
    offer_id: str
    price: Decimal
    old_price: Decimal
    min_price: Decimal
    currency: str = "RUB"

    def payload(self) -> dict:
        return {
            "offer_id": self.offer_id,
            "price": fmt_price(self.price),
            "old_price": fmt_price(self.old_price),
            "min_price": fmt_price(self.min_price),
            "currency_code": self.currency,
            "auto_action_enabled": "UNKNOWN",
            "price_strategy_enabled": "UNKNOWN",
        }


@dataclass(frozen=True)
class StockUpdate:
    offer_id: str
    product_id: int
    stock: int


def chunks(items: Sequence, size: int) -> Iterator[Sequence]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def parse_ozon_time(value: str | None) -> datetime | None:
    """'2026-10-12T08:14:03.000Z' -> aware UTC datetime."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def format_ozon_time(moment: datetime) -> str:
    """aware datetime -> '2026-10-12T08:14:03.000Z' (what filter.since / filter.to expect)."""
    utc = moment.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


class OzonClient:
    def __init__(self, transport: Transport):
        self.transport = transport

    # ---- reading -------------------------------------------------------------------------

    def list_products(self, visibility: str = "ALL", limit: int = PRODUCT_LIST_LIMIT) -> list[dict]:
        """All items of /v3/product/list, following `last_id` until a page comes back empty."""
        items: list[dict] = []
        last_id = ""
        while True:
            data = self.transport.post(
                "/v3/product/list",
                {"filter": {"visibility": visibility}, "last_id": last_id, "limit": limit},
            )
            result = data.get("result") or {}
            page = result.get("items") or []
            if not page:
                return items
            items.extend(page)
            next_id = result.get("last_id") or ""
            if not next_id or next_id == last_id:
                return items
            last_id = next_id

    def get_names(self, offer_ids: Sequence[str]) -> dict[str, str]:
        names: dict[str, str] = {}
        for batch in chunks(list(offer_ids), INFO_BATCH):
            data = self.transport.post("/v3/product/info/list", {"offer_id": list(batch)})
            for item in data.get("items") or []:
                names[str(item.get("offer_id"))] = item.get("name") or ""
        return names

    def get_prices(self, offer_ids: Sequence[str]) -> dict[str, dict]:
        prices: dict[str, dict] = {}
        for batch in chunks(list(offer_ids), INFO_BATCH):
            cursor = ""
            while True:
                data = self.transport.post(
                    "/v5/product/info/prices",
                    {"filter": {"offer_id": list(batch), "visibility": "ALL"}, "cursor": cursor, "limit": INFO_BATCH},
                )
                for item in data.get("items") or []:
                    prices[str(item["offer_id"])] = item
                cursor = data.get("cursor") or ""
                if not cursor or not data.get("items"):
                    break
        return prices

    def get_stocks(self, offer_ids: Sequence[str]) -> dict[str, dict]:
        stocks: dict[str, dict] = {}
        for batch in chunks(list(offer_ids), INFO_BATCH):
            cursor = ""
            while True:
                data = self.transport.post(
                    "/v4/product/info/stocks",
                    {"filter": {"offer_id": list(batch), "visibility": "ALL"}, "cursor": cursor, "limit": INFO_BATCH},
                )
                for item in data.get("items") or []:
                    stocks[str(item["offer_id"])] = item
                cursor = data.get("cursor") or ""
                if not cursor or not data.get("items"):
                    break
        return stocks

    def fetch_catalog(self, visibility: str = "ALL") -> list[Product]:
        """Product list + names + prices + stocks merged into Product rows (list order kept)."""
        listed = self.list_products(visibility)
        offer_ids = [str(item["offer_id"]) for item in listed]
        names = self.get_names(offer_ids)
        prices = self.get_prices(offer_ids)
        stocks = self.get_stocks(offer_ids)
        catalog: list[Product] = []
        for item in listed:
            offer_id = str(item["offer_id"])
            product = Product(offer_id=offer_id, product_id=int(item["product_id"]), name=names.get(offer_id, ""))
            price_block = (prices.get(offer_id) or {}).get("price") or {}
            product.price = to_decimal(price_block.get("price", 0))
            product.old_price = to_decimal(price_block.get("old_price", 0))
            product.min_price = to_decimal(price_block.get("min_price", 0))
            product.currency = price_block.get("currency_code") or "RUB"
            for entry in (stocks.get(offer_id) or {}).get("stocks") or []:
                if entry.get("type") == "fbs":
                    product.fbs_present = int(entry.get("present", 0))
                    product.fbs_reserved = int(entry.get("reserved", 0))
                elif entry.get("type") == "fbo":
                    product.fbo_present = int(entry.get("present", 0))
            catalog.append(product)
        return catalog

    def list_warehouses(self) -> list[dict]:
        return self.transport.post("/v1/warehouse/list", {}).get("result") or []

    def list_postings(self, since: datetime, to: datetime, status: str | None = None, page: int = POSTING_PAGE) -> list[Posting]:
        """FBS postings with in_process_at in [since, to]; pages by offset while `has_next`."""
        flt: dict = {"since": format_ozon_time(since), "to": format_ozon_time(to)}
        if status:
            flt["status"] = status
        postings: list[Posting] = []
        offset = 0
        while True:
            data = self.transport.post(
                "/v3/posting/fbs/list",
                {
                    "dir": "ASC",
                    "filter": flt,
                    "limit": page,
                    "offset": offset,
                    "with": {"analytics_data": True, "financial_data": False},
                },
            )
            result = data.get("result") or {}
            raw = result.get("postings") or []
            postings.extend(_parse_posting(p) for p in raw)
            if not result.get("has_next") or not raw:
                return postings
            offset += len(raw)

    # ---- writing -------------------------------------------------------------------------

    def update_prices(self, updates: Sequence[PriceUpdate]) -> list[ItemResult]:
        results: list[ItemResult] = []
        for batch in chunks(list(updates), PRICE_UPDATE_BATCH):
            data = self.transport.post("/v1/product/import/prices", {"prices": [u.payload() for u in batch]})
            results.extend(_item_results(data, batch))
        return results

    def update_stocks(self, updates: Sequence[StockUpdate], warehouse_id: int) -> list[ItemResult]:
        results: list[ItemResult] = []
        for batch in chunks(list(updates), STOCK_UPDATE_BATCH):
            payload = {
                "stocks": [
                    {"offer_id": u.offer_id, "product_id": u.product_id, "stock": u.stock, "warehouse_id": warehouse_id}
                    for u in batch
                ]
            }
            data = self.transport.post("/v2/products/stocks", payload)
            results.extend(_item_results(data, batch))
        return results


def _item_results(data: dict, batch: Sequence) -> list[ItemResult]:
    """Per-item outcome. An item the API did not mention at all counts as failed, not as success."""
    by_offer = {str(r.get("offer_id")): r for r in data.get("result") or []}
    out: list[ItemResult] = []
    for update in batch:
        row = by_offer.get(update.offer_id)
        if row is None:
            out.append(ItemResult(update.offer_id, False, ["нет в ответе API"]))
            continue
        errors = [f"{e.get('code', '')}: {e.get('message', '')}".strip(": ") for e in row.get("errors") or []]
        out.append(ItemResult(update.offer_id, bool(row.get("updated")) and not errors, errors))
    return out


def _parse_posting(raw: dict) -> Posting:
    analytics = raw.get("analytics_data") or {}
    delivery = raw.get("delivery_method") or {}
    lines = [
        PostingLine(
            offer_id=str(p.get("offer_id", "")),
            sku=p.get("sku"),
            name=p.get("name", ""),
            quantity=int(p.get("quantity", 0)),
            price=to_decimal(p.get("price", 0)),
            currency=p.get("currency_code") or "RUB",
        )
        for p in raw.get("products") or []
    ]
    in_process = parse_ozon_time(raw.get("in_process_at"))
    if in_process is None:
        raise ApiError(200, f"posting {raw.get('posting_number')} has no in_process_at")
    return Posting(
        posting_number=raw.get("posting_number", ""),
        order_number=raw.get("order_number", ""),
        status=raw.get("status", ""),
        in_process_at=in_process,
        shipment_date=parse_ozon_time(raw.get("shipment_date")),
        delivery_method=delivery.get("name", ""),
        city=analytics.get("city", ""),
        lines=lines,
    )
