"""Diff correctness and the dry-run / --apply contract, end to end through the CLI."""
from decimal import Decimal

from ozon_sync.cli import main
from ozon_sync.plan import build_plan, validate
from ozon_sync.sheets import read_edit_sheet

from conftest import edit_cells, write_calls

WH = "22134510000"


def _plan(path, client):
    catalog = client.fetch_catalog()
    valid, issues = validate(read_edit_sheet(path), catalog)
    assert not issues
    return build_plan(valid, catalog)


def test_untouched_export_gives_empty_diff(exported, client):
    plan = _plan(exported, client)
    assert plan.changes == [] and plan.price_updates == [] and plan.stock_updates == []
    assert plan.unchanged_rows == 14


def test_diff_lists_only_real_differences(exported, client):
    edit_cells(
        exported,
        {
            "KR-350-WH": {"price": 420, "fbs_present": 150},
            "PL-150-GR": {"old_price": 1890},
            "TR-USB-C1": {"fbs_present": 210},  # same as live -> not a change
            "SH-LED-3M": {"price": None},  # blank cell -> not a change
        },
    )
    plan = _plan(exported, client)
    summary = [(c.offer_id, c.field, c.old, c.new) for c in plan.changes]
    assert summary == [
        ("KR-350-WH", "price", Decimal("390"), Decimal("420")),
        ("KR-350-WH", "fbs_present", 120, 150),
        ("PL-150-GR", "old_price", Decimal("1790"), Decimal("1890")),
    ]
    assert plan.unchanged_rows == 12
    # a price update carries all three prices (the untouched ones keep their live value)
    cup = next(u for u in plan.price_updates if u.offer_id == "KR-350-WH")
    assert (cup.price, cup.old_price, cup.min_price) == (Decimal("420"), Decimal("520"), Decimal("340"))
    assert [(u.offer_id, u.stock) for u in plan.stock_updates] == [("KR-350-WH", 150)]


def test_decimal_text_and_comma_numbers_are_accepted(exported, client):
    edit_cells(exported, {"KR-350-WH": {"price": "480,50"}, "KR-350-BK": {"price": 395.0}})
    plan = _plan(exported, client)
    assert plan.price_updates[0].price == Decimal("480.50")
    assert plan.price_updates[0].payload()["price"] == "480.50"
    assert plan.price_updates[1].payload()["price"] == "395"  # whole numbers go without ".0"


def test_dry_run_sends_nothing(exported, fake, capsys):
    edit_cells(exported, {"KR-350-WH": {"price": 420, "fbs_present": 150}})
    code = main(["update", str(exported)], transport=fake)
    out = capsys.readouterr().out
    assert code == 0
    assert write_calls(fake) == []  # no write endpoint was called
    assert "KR-350-WH" in out and "390" in out and "420" in out and "->" in out
    assert "dry-run" in out
    assert next(p for p in fake.products if p["offer_id"] == "KR-350-WH")["price"]["price"] == "390"


def test_apply_sends_changes_and_state_changes(exported, fake, capsys):
    edit_cells(exported, {"KR-350-WH": {"price": 420, "fbs_present": 150}, "PL-150-GR": {"old_price": 1890}})
    code = main(["update", str(exported), "--apply", "--warehouse-id", WH], transport=fake)
    out = capsys.readouterr().out
    assert code == 0 and "с ошибкой: 0" in out
    (price_call,) = fake.calls_to("/v1/product/import/prices")
    assert [p["offer_id"] for p in price_call["prices"]] == ["KR-350-WH", "PL-150-GR"]
    assert price_call["prices"][0]["price"] == "420"
    (stock_call,) = fake.calls_to("/v2/products/stocks")
    assert stock_call["stocks"] == [
        {"offer_id": "KR-350-WH", "product_id": 1804000100, "stock": 150, "warehouse_id": int(WH)}
    ]
    cup = next(p for p in fake.products if p["offer_id"] == "KR-350-WH")
    assert cup["price"]["price"] == "420" and cup["stocks"][0]["present"] == 150


def test_apply_without_changes_sends_nothing(exported, fake):
    assert main(["update", str(exported), "--apply"], transport=fake) == 0
    assert write_calls(fake) == []


def test_stock_change_needs_warehouse_when_several(exported, fake, capsys):
    edit_cells(exported, {"KR-350-WH": {"fbs_present": 1}, "KR-350-BK": {"price": 400}})
    assert main(["update", str(exported), "--apply"], transport=fake) == 2
    assert "--warehouse-id" in capsys.readouterr().out
    assert write_calls(fake) == []  # the price update was not sent either: all or nothing


def test_big_price_change_is_blocked_unless_allowed(exported, fake, capsys):
    edit_cells(exported, {"PL-150-GR": {"price": 12900, "old_price": 15000}})  # 10x: a typical typo
    assert main(["update", str(exported)], transport=fake) == 0
    assert "больше 50%" in capsys.readouterr().out  # visible already in the dry-run
    assert main(["update", str(exported), "--apply"], transport=fake) == 2
    assert write_calls(fake) == []
    assert main(["update", str(exported), "--apply", "--allow-big-change"], transport=fake) == 0
    assert len(fake.calls_to("/v1/product/import/prices")) == 1


def test_api_item_error_is_reported_and_exit_code_is_1(exported, fake, capsys):
    # the API rejects a stock for an unknown warehouse per item, not with an HTTP error
    edit_cells(exported, {"KR-350-WH": {"fbs_present": 5}})
    code = main(["update", str(exported), "--apply", "--warehouse-id", "1"], transport=fake)
    out = capsys.readouterr().out
    assert code == 1
    assert "KR-350-WH" in out and "WAREHOUSE_NOT_FOUND" in out
