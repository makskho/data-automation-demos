from __future__ import annotations

import pytest

from leadrouter.normalize import (ValidationError, build_lead, clean_text, normalize_email,
                                  normalize_phone)


@pytest.mark.parametrize("raw, expected", [
    ("8 (999) 123-45-67", "+79991234567"),
    ("+7 999 123 45 67", "+79991234567"),
    ("7-999-123-45-67", "+79991234567"),
    ("9991234567", "+79991234567"),
    ("+7(495)123-45-67 доб. 12", "+74951234567"),
    ("+375 29 123-45-67", "+375291234567"),
    ("+1 415 555 2671", "+14155552671"),
])
def test_phone_ok(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12345", "+7 999 12", "1234567890", "89991234", "+79991234567890123"])
def test_phone_bad(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


@pytest.mark.parametrize("raw", ["a@b", "a b@c.ru", "@c.ru", "a@@c.ru", "a@c..ru", "a@c.r", ""])
def test_email_bad(raw):
    with pytest.raises(ValueError):
        normalize_email(raw)


def test_email_is_lowercased_and_trimmed():
    assert normalize_email("  Ivan.Petrov+crm@Mail.RU ") == "ivan.petrov+crm@mail.ru"


def test_clean_text_strips_control_chars_and_caps_length():
    assert clean_text("Иван\r\nBcc: x@y.ru\x00") == "Иван Bcc: x@y.ru"  # no NUL, one line
    assert clean_text("a\r\nb\rc", multiline=True) == "a\nb\nc"
    assert clean_text(None) == "" and clean_text(["а", "б"]) == "а, б"
    assert len(clean_text("x" * 10_000, 50)) == 50


def test_header_injection_cannot_reach_email_headers():
    lead = build_lead({"name": "Иван\r\nBcc: evil@x.ru", "email": "i@example.com"}, "json", 0)
    assert lead.name == "Иван Bcc: evil@x.ru"  # one line, so EmailMessage accepts it in Subject


def test_validation_collects_all_errors():
    with pytest.raises(ValidationError) as err:
        build_lead({"phone": "1", "email": "x"}, "json", 0)
    assert set(err.value.errors) == {"phone", "email"}


def test_field_aliases_and_case_insensitive_keys():
    lead = build_lead({"NAME": "А", "TEL": "89990001122", "E-Mail": "a@b.ru", "Comments": "т"}, "form", 0)
    assert (lead.name, lead.phone, lead.email, lead.message) == ("А", "+79990001122", "a@b.ru", "т")
