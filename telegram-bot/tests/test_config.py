import pytest

from bot.config import ConfigError, load_settings


def test_valid_env_with_defaults():
    s = load_settings({"BOT_TOKEN": "123:abc", "ADMIN_CHAT_ID": "-100123"})
    assert s.admin_chat_id == -100123
    assert (s.db_path, s.faq_path, s.flood_minutes) == ("leads.db", "faq.yaml", 10)


def test_overrides():
    s = load_settings(
        {"BOT_TOKEN": "123:abc", "ADMIN_CHAT_ID": "5", "DB_PATH": "x.db", "FAQ_PATH": "f.json", "FLOOD_MINUTES": "0"}
    )
    assert (s.db_path, s.faq_path, s.flood_minutes) == ("x.db", "f.json", 0)


@pytest.mark.parametrize(
    "env, fragment",
    [
        ({"ADMIN_CHAT_ID": "1"}, "BOT_TOKEN не задан"),
        ({"BOT_TOKEN": "nocolon", "ADMIN_CHAT_ID": "1"}, "выглядит неверно"),
        ({"BOT_TOKEN": "1:a"}, "ADMIN_CHAT_ID не задан"),
        ({"BOT_TOKEN": "1:a", "ADMIN_CHAT_ID": "me"}, "должен быть числом"),
        ({"BOT_TOKEN": "1:a", "ADMIN_CHAT_ID": "1", "FLOOD_MINUTES": "x"}, "FLOOD_MINUTES"),
        ({"BOT_TOKEN": "1:a", "ADMIN_CHAT_ID": "1", "FLOOD_MINUTES": "-1"}, "отрицательным"),
    ],
)
def test_bad_env_gives_readable_error(env, fragment):
    with pytest.raises(ConfigError, match=fragment):
        load_settings(env)
