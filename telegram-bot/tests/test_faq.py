import json

import pytest

from bot.faq import ROOT_ID, FaqError, load_faq, parse_faq
from bot.keyboards import main_menu, node_menu

from conftest import FAQ_PATH


def minimal(**override):
    data = {"welcome": "Привет", "items": [{"id": "a", "title": "A", "text": "ответ"}]}
    data.update(override)
    return data


def test_shipped_faq_file_is_valid_and_nested():
    tree = load_faq(FAQ_PATH)
    assert tree.welcome
    assert [n.id for n in tree.roots][:2] == ["services", "prices"]
    bots = tree.get("services-bots")
    assert bots.parent_id == "services"
    assert [c.id for c in bots.children] == ["services-bots-faq", "services-bots-leads"]
    assert tree.get("services-bots-faq").parent_id == "services-bots"
    assert tree.get("services").parent_id == ROOT_ID


def test_json_file_is_loaded(tmp_path):
    path = tmp_path / "faq.json"
    path.write_text(json.dumps(minimal(), ensure_ascii=False), encoding="utf-8")
    assert load_faq(path).get("a").text == "ответ"


def test_missing_file_is_a_readable_error(tmp_path):
    with pytest.raises(FaqError, match="не удалось прочитать"):
        load_faq(tmp_path / "nope.yaml")


def test_broken_yaml_is_a_readable_error(tmp_path):
    path = tmp_path / "faq.yaml"
    path.write_text("welcome: [unclosed", encoding="utf-8")
    with pytest.raises(FaqError, match="не разобран"):
        load_faq(path)


@pytest.mark.parametrize(
    "data, fragment",
    [
        ([], "словарём"),
        (minimal(welcome=""), "welcome"),
        (minimal(items=[]), "items"),
        (minimal(items=["строка"]), r"items\[0\]"),
        (minimal(items=[{"id": "Bad Id", "title": "A", "text": "t"}]), "id должен"),
        (minimal(items=[{"id": "root", "title": "A", "text": "t"}]), "зарезервирован"),
        (minimal(items=[{"id": "a", "text": "t"}]), "нет title"),
        (minimal(items=[{"id": "a", "title": "x" * 61, "text": "t"}]), "title длиннее"),
        (minimal(items=[{"id": "a", "title": "A"}]), "должен быть text"),
        (minimal(items=[{"id": "a", "title": "A", "text": "x" * 4001}]), "text длиннее"),
        (minimal(items=[{"id": "a", "title": "A", "text": "t", "children": "oops"}]), "children"),
    ],
)
def test_invalid_trees_are_rejected_with_location(data, fragment):
    with pytest.raises(FaqError, match=fragment):
        parse_faq(data)


def test_duplicate_id_is_rejected_even_across_levels():
    data = minimal(
        items=[
            {"id": "a", "title": "A", "text": "t"},
            {"id": "b", "title": "B", "children": [{"id": "a", "title": "dup", "text": "t"}]},
        ]
    )
    with pytest.raises(FaqError, match=r"items\[1\]\.children\[0\].*'a' повторяется"):
        parse_faq(data)


def test_node_with_children_needs_no_text():
    tree = parse_faq(
        minimal(items=[{"id": "g", "title": "G", "children": [{"id": "c", "title": "C", "text": "t"}]}])
    )
    assert tree.get("g").children[0].id == "c"


def test_callback_data_fits_telegram_limit():
    tree = load_faq(FAQ_PATH)
    markups = [main_menu(tree)] + [node_menu(n) for n in tree.nodes.values()]
    for markup in markups:
        for row in markup.inline_keyboard:
            for button in row:
                assert len(button.callback_data.encode()) <= 64


def test_menu_has_back_buttons_and_lead_button_on_leaf():
    tree = load_faq(FAQ_PATH)
    top = [b.callback_data for row in main_menu(tree).inline_keyboard for b in row]
    assert top[-1] == "lead"
    nested = [b.callback_data for row in node_menu(tree.get("services-bots-faq")).inline_keyboard for b in row]
    assert nested == ["lead", "n:services-bots", "n:root"]
    first_level = [b.callback_data for row in node_menu(tree.get("prices")).inline_keyboard for b in row]
    assert first_level == ["lead", "n:root"]
