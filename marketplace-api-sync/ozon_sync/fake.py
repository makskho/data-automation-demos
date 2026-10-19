"""In-memory stand-in for the Ozon Seller API (a Transport), used by the tests and by `--demo`.

It mimics the parts of the contract the client depends on: `last_id` / `cursor` / `offset`
pagination, per-request size limits (400 when exceeded), per-item update errors and date
filtering of postings. State changes made by the update endpoints stay in memory only.
The bundled fixtures are SYNTHETIC (invented shop, invented numbers), not Ozon data.
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .client import (
    INFO_BATCH,
    PRICE_UPDATE_BATCH,
    PRODUCT_LIST_LIMIT,
    STOCK_UPDATE_BATCH,
    parse_ozon_time,
)
from .errors import ApiError

FIXTURE_DIR = Path(__file__).parent / "fixtures"
POSTING_MAX_PAGE = 1000


def load_fixture(name: str) -> dict:
    with open(FIXTURE_DIR / name, encoding="utf-8") as handle:
        return json.load(handle)


class FakeOzon:
    def __init__(self, products: list[dict] | None = None, postings: list[dict] | None = None, warehouses: list[dict] | None = None):
        base = load_fixture("products.json") if products is None or warehouses is None else {}
        self.products: list[dict] = copy.deepcopy(products if products is not None else base["products"])
        self.warehouses: list[dict] = copy.deepcopy(warehouses if warehouses is not None else base["warehouses"])
        self.postings: list[dict] = copy.deepcopy(postings if postings is not None else load_fixture("postings.json")["postings"])
        self.calls: list[tuple[str, dict]] = []

    # ---- Transport -----------------------------------------------------------------------

    def post(self, path: str, payload: dict) -> dict:
        self.calls.append((path, copy.deepcopy(payload)))
        handler = {
            "/v3/product/list": self._product_list,
            "/v3/product/info/list": self._info_list,
            "/v5/product/info/prices": self._prices,
            "/v4/product/info/stocks": self._stocks,
            "/v2/products/stocks": self._set_stocks,
            "/v1/product/import/prices": self._set_prices,
            "/v3/posting/fbs/list": self._postings,
            "/v1/warehouse/list": lambda _p: {"result": self.warehouses},
        }.get(path)
        if handler is None:
            raise ApiError(404, f"unknown method {path}")
        return handler(payload)

    def calls_to(self, path: str) -> list[dict]:
        return [payload for p, payload in self.calls if p == path]

    # ---- helpers -------------------------------------------------------------------------

    def _find(self, offer_id: str) -> dict | None:
        return next((p for p in self.products if p["offer_id"] == offer_id), None)

    @staticmethod
    def _check_limit(value: Any, maximum: int, what: str) -> int:
        if not isinstance(value, int) or not 1 <= value <= maximum:
            raise ApiError(400, f"{what} must be between 1 and {maximum}")
        return value

    def _selected(self, payload: dict) -> list[dict]:
        flt = payload.get("filter") or {}
        offer_ids = flt.get("offer_id") or []
        if len(offer_ids) > INFO_BATCH:
            raise ApiError(400, f"filter.offer_id: at most {INFO_BATCH} values")
        selected = [p for p in self.products if not offer_ids or p["offer_id"] in offer_ids]
        return selected

    @staticmethod
    def _page_by_cursor(rows: list[dict], payload: dict) -> tuple[list[dict], str]:
        limit = FakeOzon._check_limit(payload.get("limit"), INFO_BATCH, "limit")
        start = int((payload.get("cursor") or "c0")[1:])
        page = rows[start : start + limit]
        nxt = start + len(page)
        return page, (f"c{nxt}" if nxt < len(rows) else "")

    # ---- handlers ------------------------------------------------------------------------

    def _product_list(self, payload: dict) -> dict:
        limit = self._check_limit(payload.get("limit"), PRODUCT_LIST_LIMIT, "limit")
        visibility = (payload.get("filter") or {}).get("visibility", "ALL")
        rows = [p for p in self.products if visibility == "ALL" or not p.get("archived")]
        start = int((payload.get("last_id") or "p0")[1:])
        page = rows[start : start + limit]
        last_id = f"p{start + len(page)}" if page else (payload.get("last_id") or "")
        items = [
            {
                "product_id": p["product_id"],
                "offer_id": p["offer_id"],
                "has_fbo_stocks": any(s["type"] == "fbo" and s["present"] for s in p["stocks"]),
                "has_fbs_stocks": any(s["type"] == "fbs" and s["present"] for s in p["stocks"]),
                "archived": p.get("archived", False),
                "is_discounted": False,
                "quants": [],
            }
            for p in page
        ]
        return {"result": {"items": items, "total": len(rows), "last_id": last_id}}

    def _info_list(self, payload: dict) -> dict:
        offer_ids = payload.get("offer_id") or []
        if len(offer_ids) > INFO_BATCH:
            raise ApiError(400, f"offer_id: at most {INFO_BATCH} values")
        items = [
            {"id": p["product_id"], "offer_id": p["offer_id"], "name": p["name"], "sku": p.get("sku")}
            for p in self.products
            if p["offer_id"] in offer_ids
        ]
        return {"items": items}

    def _prices(self, payload: dict) -> dict:
        rows = self._selected(payload)
        page, cursor = self._page_by_cursor(rows, payload)
        items = [
            {
                "offer_id": p["offer_id"],
                "product_id": p["product_id"],
                "price": {
                    "price": p["price"]["price"],
                    "old_price": p["price"]["old_price"],
                    "min_price": p["price"]["min_price"],
                    "net_price": p["price"].get("net_price", 0),
                    "currency_code": p["price"].get("currency_code", "RUB"),
                },
            }
            for p in page
        ]
        return {"items": items, "total": len(rows), "cursor": cursor}

    def _stocks(self, payload: dict) -> dict:
        rows = self._selected(payload)
        page, cursor = self._page_by_cursor(rows, payload)
        items = [{"offer_id": p["offer_id"], "product_id": p["product_id"], "stocks": p["stocks"]} for p in page]
        return {"items": items, "total": len(rows), "cursor": cursor}

    def _set_stocks(self, payload: dict) -> dict:
        stocks = payload.get("stocks") or []
        if not 1 <= len(stocks) <= STOCK_UPDATE_BATCH:
            raise ApiError(400, f"stocks: between 1 and {STOCK_UPDATE_BATCH} items per request")
        known_warehouses = {w["warehouse_id"] for w in self.warehouses}
        result = []
        for item in stocks:
            row = {"offer_id": item["offer_id"], "product_id": item["product_id"], "warehouse_id": item["warehouse_id"]}
            product = self._find(item["offer_id"])
            errors = []
            if product is None:
                errors.append({"code": "PRODUCT_NOT_FOUND", "message": "Product not found"})
            if item["warehouse_id"] not in known_warehouses:
                errors.append({"code": "WAREHOUSE_NOT_FOUND", "message": "Warehouse not found"})
            if not isinstance(item["stock"], int) or item["stock"] < 0:
                errors.append({"code": "INVALID_STOCK", "message": "stock must be a non-negative integer"})
            if not errors:
                fbs = next((s for s in product["stocks"] if s["type"] == "fbs"), None)
                if fbs is None:
                    fbs = {"type": "fbs", "present": 0, "reserved": 0}
                    product["stocks"].append(fbs)
                fbs["present"] = item["stock"]
            result.append({**row, "updated": not errors, "errors": errors})
        return {"result": result}

    def _set_prices(self, payload: dict) -> dict:
        prices = payload.get("prices") or []
        if not 1 <= len(prices) <= PRICE_UPDATE_BATCH:
            raise ApiError(400, f"prices: between 1 and {PRICE_UPDATE_BATCH} items per request")
        result = []
        for item in prices:
            product = self._find(item["offer_id"])
            errors = []
            if product is None:
                errors.append({"code": "PRODUCT_NOT_FOUND", "message": "Product not found"})
            else:
                try:
                    price = Decimal(item["price"])
                    old = Decimal(item.get("old_price", "0"))
                    minimum = Decimal(item.get("min_price", "0"))
                except Exception:
                    errors.append({"code": "INVALID_PRICE", "message": "price fields must be numeric strings"})
                else:
                    if old and old <= price:
                        errors.append({"code": "OLD_PRICE_TOO_LOW", "message": "old_price must be greater than price"})
                    if minimum and minimum > price:
                        errors.append({"code": "MIN_PRICE_TOO_HIGH", "message": "min_price must not exceed price"})
                    if not errors:
                        block = product["price"]
                        block["price"], block["old_price"], block["min_price"] = str(price), str(old), str(minimum)
            result.append(
                {
                    "offer_id": item["offer_id"],
                    "product_id": product["product_id"] if product else 0,
                    "updated": not errors,
                    "errors": errors,
                }
            )
        return {"result": result}

    def _postings(self, payload: dict) -> dict:
        limit = self._check_limit(payload.get("limit"), POSTING_MAX_PAGE, "limit")
        offset = payload.get("offset", 0)
        flt = payload.get("filter") or {}
        since, to = parse_ozon_time(flt.get("since")), parse_ozon_time(flt.get("to"))
        if since is None or to is None:
            raise ApiError(400, "filter.since and filter.to are required")
        rows = [
            p
            for p in self.postings
            if since <= parse_ozon_time(p["in_process_at"]) <= to and (not flt.get("status") or p["status"] == flt["status"])
        ]
        rows.sort(key=lambda p: parse_ozon_time(p["in_process_at"]), reverse=(payload.get("dir") == "DESC"))
        page = rows[offset : offset + limit]
        return {"result": {"postings": page, "has_next": offset + len(page) < len(rows)}}
