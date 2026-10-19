"""Validation of the seller's sheet: nothing is sent when it is wrong."""
import pytest
from openpyxl import Workbook

from ozon_sync.cli import main
from ozon_sync.errors import SheetError
from ozon_sync.plan import validate
from ozon_sync.sheets import read_edit_sheet

from conftest import edit_cells, write_calls


def _issues(path, client):
    _, issues = validate(read_edit_sheet(path), client.fetch_catalog())
    return {(i.offer_id, i.code) for i in issues}


def test_unknown_sku_is_reported(exported, client):
    edit_cells(exported, {}, extra=[{"offer_id": "NO-SUCH-SKU", "price": 500}])
    assert _issues(exported, client) == {("NO-SUCH-SKU", "unknown_sku")}


def test_negative_and_fractional_stock(exported, client):
    edit_cells(exported, {"CT-BAM-S": {"fbs_present": -5}, "CT-BAM-L": {"fbs_present": 2.5}})
    assert _issues(exported, client) == {("CT-BAM-S", "negative_stock"), ("CT-BAM-L", "fractional_stock")}


def test_whole_float_stock_is_fine(exported, client):
    edit_cells(exported, {"CT-BAM-S": {"fbs_present": 7.0}})  # Excel often stores 7 as 7.0
    assert _issues(exported, client) == set()


def test_text_instead_of_number(exported, client):
    edit_cells(exported, {"OR-BOX-3": {"price": "тысяча"}, "LM-DSK-W": {"fbs_present": "много"}})
    assert _issues(exported, client) == {("OR-BOX-3", "bad_number"), ("LM-DSK-W", "bad_number")}


def test_price_rules(exported, client):
    edit_cells(
        exported,
        {
            "KR-350-WH": {"price": 0},
            "KR-350-BK": {"price": -10},
            "PL-150-GR": {"price": 1900},  # old price 1790 now below the price
            "PL-150-BE": {"min_price": 1500},  # above the price 1290
        },
    )
    assert _issues(exported, client) == {
        ("KR-350-WH", "price_not_positive"),
        ("KR-350-BK", "negative_price"),
        ("PL-150-GR", "old_price_below_price"),
        ("PL-150-BE", "min_price_above_price"),
    }


def test_duplicate_and_empty_sku(exported, client):
    edit_cells(exported, {}, extra=[{"offer_id": "KR-350-WH", "price": 400}, {"offer_id": None, "price": 400}])
    codes = _issues(exported, client)
    assert ("KR-350-WH", "duplicate") in codes and ("", "empty_sku") in codes


def test_invalid_sheet_blocks_the_whole_run_even_with_apply(exported, fake, capsys):
    edit_cells(exported, {"KR-350-WH": {"price": 420}, "CT-BAM-S": {"fbs_present": -5}})
    code = main(["update", str(exported), "--apply", "--warehouse-id", "22134510000"], transport=fake)
    out = capsys.readouterr().out
    assert code == 2
    assert "negative_stock" in out and "CT-BAM-S" in out and "Ничего не отправлено" in out
    assert write_calls(fake) == []  # the valid row was not sent either


def test_skip_invalid_sends_only_the_good_rows(exported, fake, capsys):
    edit_cells(exported, {"KR-350-WH": {"price": 420}, "CT-BAM-S": {"fbs_present": -5}})
    code = main(["update", str(exported), "--apply", "--skip-invalid"], transport=fake)
    assert code == 0
    (call,) = fake.calls_to("/v1/product/import/prices")
    assert [p["offer_id"] for p in call["prices"]] == ["KR-350-WH"]
    assert fake.calls_to("/v2/products/stocks") == []


def test_bad_row_numbers_point_at_the_excel_row(exported, client):
    rows = edit_cells(exported, {"CT-BAM-S": {"fbs_present": -5}})
    _, issues = validate(read_edit_sheet(exported), client.fetch_catalog())
    assert issues[0].row_no == rows["CT-BAM-S"]


def test_file_without_sku_column_is_rejected(tmp_path):
    wb = Workbook()
    wb.active.append(["Название", "Цена"])
    wb.active.append(["Кружка", 100])
    path = tmp_path / "x.xlsx"
    wb.save(path)
    with pytest.raises(SheetError, match="offer_id"):
        read_edit_sheet(path)


def test_missing_and_corrupt_files(tmp_path, fake, capsys):
    assert main(["update", str(tmp_path / "nope.xlsx")], transport=fake) == 2
    broken = tmp_path / "broken.xlsx"
    broken.write_text("this is not a workbook")
    assert main(["update", str(broken)], transport=fake) == 2
    assert fake.calls == []  # failed before any request
    assert "Ошибка файла" in capsys.readouterr().err


def test_numeric_sku_cells_are_read_as_text(tmp_path, client):
    wb = Workbook()
    ws = wb.active
    ws.append(["Артикул (offer_id)", "Цена"])
    ws.append([12345.0, 100])  # Excel turned the SKU into a number
    path = tmp_path / "x.xlsx"
    wb.save(path)
    assert read_edit_sheet(path)[0].offer_id == "12345"
