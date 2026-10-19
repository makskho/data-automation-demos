from ozon_sync.client import OzonClient
from ozon_sync.fake import FakeOzon

from conftest import synthetic_products


def test_product_list_follows_last_id_until_empty_page(fake, client):
    items = client.list_products(limit=5)
    assert [i["offer_id"] for i in items] == [p["offer_id"] for p in fake.products]  # all 14, in order
    calls = fake.calls_to("/v3/product/list")
    # 5 + 5 + 4 items, then one empty page ends the loop
    assert [c["last_id"] for c in calls] == ["", "p5", "p10", "p14"]
    assert all(c["limit"] == 5 for c in calls)


def test_product_list_default_page_size_is_1000():
    fake = FakeOzon(products=synthetic_products(2500))
    items = OzonClient(fake).list_products()
    assert len(items) == 2500
    assert len({i["offer_id"] for i in items}) == 2500  # no duplicates across pages
    assert [c["limit"] for c in fake.calls_to("/v3/product/list")] == [1000] * 4  # 1000, 1000, 500, empty


def test_product_list_empty_shop():
    fake = FakeOzon(products=[])
    assert OzonClient(fake).list_products() == []
    assert len(fake.calls_to("/v3/product/list")) == 1


class ScriptedTransport:
    """Returns canned pages in order and records the requests."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.requests = []

    def post(self, path, payload):
        self.requests.append((path, payload))
        return self.pages.pop(0)


def _price_item(offer_id):
    return {"offer_id": offer_id, "product_id": 1, "price": {"price": 100, "old_price": 0, "min_price": 0}}


def test_prices_follow_cursor():
    transport = ScriptedTransport(
        [
            {"items": [_price_item("A"), _price_item("B")], "cursor": "next-1"},
            {"items": [_price_item("C")], "cursor": ""},
        ]
    )
    prices = OzonClient(transport).get_prices(["A", "B", "C"])
    assert set(prices) == {"A", "B", "C"}
    assert [r[1]["cursor"] for r in transport.requests] == ["", "next-1"]


def test_fetch_catalog_merges_names_prices_and_stocks(client):
    catalog = {p.offer_id: p for p in client.fetch_catalog()}
    cup = catalog["KR-350-WH"]
    assert (cup.name, int(cup.price), int(cup.old_price), int(cup.min_price)) == ("Кружка керамическая 350 мл, белая", 390, 520, 340)
    assert (cup.fbs_present, cup.fbs_reserved, cup.fbo_present) == (120, 4, 80)
    assert len(catalog) == 14
