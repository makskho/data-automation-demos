from decimal import Decimal

from ozon_sync.client import (
    INFO_BATCH,
    PRICE_UPDATE_BATCH,
    STOCK_UPDATE_BATCH,
    OzonClient,
    PriceUpdate,
    StockUpdate,
    chunks,
)
from ozon_sync.fake import FakeOzon

from conftest import synthetic_products


def test_chunks_helper():
    assert [len(c) for c in chunks(list(range(7)), 3)] == [3, 3, 1]
    assert list(chunks([], 3)) == []


def test_stock_updates_are_sent_in_batches_of_100():
    fake = FakeOzon(products=synthetic_products(250))
    updates = [StockUpdate(p["offer_id"], p["product_id"], 7) for p in fake.products]
    results = OzonClient(fake).update_stocks(updates, warehouse_id=22134510000)
    sizes = [len(c["stocks"]) for c in fake.calls_to("/v2/products/stocks")]
    assert sizes == [100, 100, 50] and max(sizes) <= STOCK_UPDATE_BATCH
    assert len(results) == 250 and all(r.ok for r in results)
    assert all(p["stocks"][0]["present"] == 7 for p in fake.products)  # each item applied exactly once


def test_price_updates_are_sent_in_batches_of_1000():
    fake = FakeOzon(products=synthetic_products(2300))
    updates = [PriceUpdate(p["offer_id"], Decimal("120"), Decimal("150"), Decimal("90")) for p in fake.products]
    results = OzonClient(fake).update_prices(updates)
    sizes = [len(c["prices"]) for c in fake.calls_to("/v1/product/import/prices")]
    assert sizes == [1000, 1000, 300] and max(sizes) <= PRICE_UPDATE_BATCH
    assert len(results) == 2300 and all(r.ok for r in results)


def test_exact_multiple_does_not_send_an_empty_batch():
    fake = FakeOzon(products=synthetic_products(200))
    updates = [StockUpdate(p["offer_id"], p["product_id"], 1) for p in fake.products]
    OzonClient(fake).update_stocks(updates, 22134510000)
    assert [len(c["stocks"]) for c in fake.calls_to("/v2/products/stocks")] == [100, 100]


def test_no_updates_no_requests():
    fake = FakeOzon(products=synthetic_products(3))
    client = OzonClient(fake)
    assert client.update_stocks([], 22134510000) == [] and client.update_prices([]) == []
    assert fake.calls == []


def test_info_requests_respect_the_offer_id_limit():
    fake = FakeOzon(products=synthetic_products(2500))
    catalog = OzonClient(fake).fetch_catalog()
    assert len(catalog) == 2500 and all(p.name for p in catalog)
    for path in ("/v3/product/info/list", "/v5/product/info/prices", "/v4/product/info/stocks"):
        calls = fake.calls_to(path)
        sent = [c["offer_id"] if path.endswith("list") else c["filter"]["offer_id"] for c in calls]
        assert [len(s) for s in sent] == [1000, 1000, 500]
        assert max(len(s) for s in sent) <= INFO_BATCH


def test_fake_rejects_oversized_batches_like_the_real_api():
    # guards the guard: if the fake did not enforce limits the batching tests above would prove nothing
    import pytest

    from ozon_sync.errors import ApiError

    fake = FakeOzon(products=synthetic_products(150))
    too_many = [{"offer_id": p["offer_id"], "product_id": p["product_id"], "stock": 1, "warehouse_id": 22134510000} for p in fake.products]
    with pytest.raises(ApiError) as caught:
        fake.post("/v2/products/stocks", {"stocks": too_many})
    assert caught.value.status == 400
