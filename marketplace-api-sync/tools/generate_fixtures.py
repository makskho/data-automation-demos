"""Regenerate ozon_sync/fixtures/*.json. SYNTHETIC data: an invented shop, invented numbers.

    python tools/generate_fixtures.py
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "ozon_sync" / "fixtures"

META = {
    "synthetic": True,
    "note": "Synthetic demo data in the shape of Ozon Seller API responses. Not real shop data.",
}

# offer_id, name, price, old_price, min_price, net_price, fbs present, fbs reserved, fbo present
PRODUCTS = [
    ("KR-350-WH", "Кружка керамическая 350 мл, белая", 390, 520, 340, 150, 120, 4, 80),
    ("KR-350-BK", "Кружка керамическая 350 мл, чёрная", 390, 520, 340, 150, 95, 2, 60),
    ("PL-150-GR", "Плед флисовый 150x200 см, серый", 1290, 1790, 1100, 520, 34, 3, 12),
    ("PL-150-BE", "Плед флисовый 150x200 см, бежевый", 1290, 1790, 1100, 520, 41, 0, 0),
    ("PD-5050-2", "Наволочка декоративная 50x50 см, 2 шт.", 560, 0, 480, 210, 77, 5, 40),
    ("SH-LED-3M", "Светодиодная лента 3 м, тёплый белый", 740, 990, 650, 300, 0, 0, 25),
    ("CT-BAM-S", "Разделочная доска бамбуковая, S", 450, 0, 380, 160, 58, 1, 0),
    ("CT-BAM-L", "Разделочная доска бамбуковая, L", 830, 1100, 720, 340, 19, 2, 9),
    ("OR-BOX-3", "Органайзер для хранения, набор 3 шт.", 1150, 1490, 990, 480, 26, 0, 14),
    ("TR-USB-C1", "Кабель USB-C 1 м, плетёный", 320, 450, 270, 90, 210, 11, 150),
    ("TR-USB-C2", "Кабель USB-C 2 м, плетёный", 410, 590, 350, 120, 162, 6, 98),
    ("LM-DSK-W", "Лампа настольная, белая", 1890, 2490, 1650, 760, 12, 1, 0),
    ("SP-MST-6", "Набор кухонных ёмкостей для специй, 6 шт.", 980, 1290, 850, 400, 44, 2, 31),
    ("HK-ADH-10", "Крючки самоклеящиеся, 10 шт.", 190, 0, 160, 55, 0, 0, 0),
]

WAREHOUSES = [
    {"warehouse_id": 22134510000, "name": "Основной склад (Москва)", "is_rfbs": False, "status": "created"},
    {"warehouse_id": 22134510001, "name": "Склад Подольск", "is_rfbs": False, "status": "created"},
]

# posting_number, in_process_at (UTC), status, city, delivery, [(offer_id, qty)]
POSTINGS = [
    ("48172950-0001-1", "2026-10-01T06:12:44.000Z", "delivered", "Москва", "Ozon Логистика курьер", [("KR-350-WH", 2)]),
    ("48172950-0002-1", "2026-10-02T09:40:10.000Z", "delivered", "Казань", "Ozon Логистика ПВЗ", [("PL-150-GR", 1), ("PD-5050-2", 1)]),
    ("48201377-0001-1", "2026-10-03T17:05:31.000Z", "cancelled", "Самара", "Ozon Логистика ПВЗ", [("SH-LED-3M", 1)]),
    ("48230981-0001-1", "2026-10-05T20:48:02.000Z", "delivered", "Санкт-Петербург", "Ozon Логистика курьер", [("TR-USB-C1", 3)]),
    ("48257404-0001-1", "2026-10-07T08:20:55.000Z", "delivering", "Екатеринбург", "Ozon Логистика ПВЗ", [("CT-BAM-L", 1), ("CT-BAM-S", 1)]),
    ("48257404-0002-1", "2026-10-07T21:59:59.000Z", "delivering", "Новосибирск", "Ozon Логистика ПВЗ", [("OR-BOX-3", 1)]),
    ("48290215-0001-1", "2026-10-08T00:00:00.000Z", "delivering", "Москва", "Ozon Логистика курьер", [("LM-DSK-W", 1)]),
    ("48311862-0001-1", "2026-10-09T11:31:18.000Z", "awaiting_deliver", "Нижний Новгород", "Ozon Логистика ПВЗ", [("SP-MST-6", 2)]),
    ("48335740-0001-1", "2026-10-10T14:02:40.000Z", "awaiting_deliver", "Краснодар", "Ozon Логистика курьер", [("TR-USB-C2", 1), ("TR-USB-C1", 1)]),
    ("48358126-0001-1", "2026-10-12T07:45:12.000Z", "awaiting_packaging", "Москва", "Ozon Логистика курьер", [("KR-350-BK", 4)]),
    ("48358126-0002-1", "2026-10-12T10:11:37.000Z", "awaiting_packaging", "Воронеж", "Ozon Логистика ПВЗ", [("PL-150-BE", 1)]),
    ("48381593-0001-1", "2026-10-14T05:30:00.000Z", "awaiting_packaging", "Пермь", "Ozon Логистика ПВЗ", [("PD-5050-2", 2), ("CT-BAM-S", 2)]),
]


def build_products():
    items = []
    for index, (offer_id, name, price, old, minimum, net, fbs, reserved, fbo) in enumerate(PRODUCTS):
        items.append(
            {
                "product_id": 1_804_000_100 + index * 7,
                "sku": 1_480_300_000 + index * 13,
                "offer_id": offer_id,
                "name": name,
                "archived": False,
                "price": {
                    "price": str(price),
                    "old_price": str(old),
                    "min_price": str(minimum),
                    "net_price": str(net),
                    "currency_code": "RUB",
                },
                "stocks": [
                    {"type": "fbs", "present": fbs, "reserved": reserved},
                    {"type": "fbo", "present": fbo, "reserved": 0},
                ],
            }
        )
    return items


def build_postings(products):
    by_offer = {p["offer_id"]: p for p in products}
    out = []
    for number, created, status, city, delivery, lines in POSTINGS:
        hour = int(created[11:13])
        ship_day = int(created[8:10]) + 2
        out.append(
            {
                "posting_number": number,
                "order_id": 53_000_000_000 + int(number[:8]) % 1_000_000,
                "order_number": number.rsplit("-", 1)[0],
                "status": status,
                "delivery_method": {"id": 1001, "name": delivery, "warehouse": "Основной склад (Москва)"},
                "tracking_number": "",
                "in_process_at": created,
                "shipment_date": f"2026-10-{ship_day:02d}T{max(hour, 9):02d}:00:00.000Z",
                "products": [
                    {
                        "sku": by_offer[offer]["sku"],
                        "name": by_offer[offer]["name"],
                        "offer_id": offer,
                        "quantity": qty,
                        "price": f"{by_offer[offer]['price']['price']}.0000",
                        "currency_code": "RUB",
                    }
                    for offer, qty in lines
                ],
                "analytics_data": {"city": city, "region": "", "delivery_type": "PVZ", "payment_type_group_name": "Карты оплаты"},
            }
        )
    return out


def main():
    products = build_products()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "products.json").write_text(
        json.dumps({"_meta": META, "warehouses": WAREHOUSES, "products": products}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "postings.json").write_text(
        json.dumps({"_meta": META, "postings": build_postings(products)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(products)} products, {len(POSTINGS)} postings -> {OUT}")


if __name__ == "__main__":
    main()
