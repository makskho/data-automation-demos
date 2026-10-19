import pytest

from bot.validators import normalize_phone, validate_name, validate_phone, validate_task


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("+7 999 123-45-67", "+79991234567"),
        ("8 (999) 123-45-67", "+79991234567"),
        ("89991234567", "+79991234567"),
        ("79991234567", "+79991234567"),
        ("9991234567", "+79991234567"),
        ("  +7(999)123 45 67 ", "+79991234567"),
        ("+375 29 123-45-67", "+375291234567"),
        ("+1 202 555 0143", "+12025550143"),
    ],
)
def test_valid_phones_are_normalized(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "abc",
        "12345",
        "+7 999 123-45",  # не хватает цифр
        "+7 999 123-45-678",  # лишняя цифра
        "8 (999) 123-45-6a",
        "29991234567",  # не 7/8 в начале
        "+7 199 123-45-67",  # код, которого нет в РФ
        "+1234567890123456",  # длиннее 15 цифр
        "999-12-34 доб. 5",
        "=1+1",
    ],
)
def test_invalid_phones_are_rejected(raw):
    assert normalize_phone(raw) is None
    value, error = validate_phone(raw)
    assert value is None and "Пример" in error


@pytest.mark.parametrize("raw", ["Иван", "  Анна   Мария ", "Жан-Пьер", "O'Neil", "Иван П."])
def test_valid_names(raw):
    name, error = validate_name(raw)
    assert error is None and name == " ".join(raw.split())


@pytest.mark.parametrize("raw", ["", "И", "Иван123", "12345", "@@@", "x" * 61, "/start"])
def test_invalid_names(raw):
    name, error = validate_name(raw)
    assert name is None and error


def test_task_length_bounds():
    assert validate_task("коротко")[1] is not None
    assert validate_task("Нужен бот для записи клиентов")[1] is None
    assert validate_task("я" * 1001)[1] is not None
    assert validate_task("  " + "я" * 20 + "  ")[0] == "я" * 20
