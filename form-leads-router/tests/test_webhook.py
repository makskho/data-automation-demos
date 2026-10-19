"""End-to-end through the HTTP layer with fake sinks."""
from __future__ import annotations

from conftest import TILDA_FORM


def post_tilda(client, **over):
    return client.post("/webhook", data={**TILDA_FORM, **over})  # form-urlencoded, UTF-8


def test_tilda_payload_with_cyrillic_is_parsed_and_fanned_out(client, sinks):
    resp = post_tilda(client)
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "ok"
    for sink in sinks.values():
        assert len(sink.sent) == 1
    lead = sinks["sheets"].sent[0]
    assert lead.name == "Анна Петрова"
    assert lead.phone == "+79991234567"
    assert lead.email == "anna.petrova@example.com"
    assert lead.message == "Нужен лендинг на Тильде, срок — две недели."
    assert lead.source == "tilda"
    assert lead.form == "form123456"
    assert lead.tranid == "1234567:8901234"
    assert "cookies" not in lead.extra and "tranid" not in lead.extra


def test_tilda_extra_fields_are_kept(client, sinks):
    post_tilda(client, Город="Казань", Budget="50 000")
    assert sinks["sheets"].sent[0].extra == {"Город": "Казань", "Budget": "50 000"}


def test_json_payload_from_wordpress_cf7(client, sinks):
    resp = client.post("/webhook", json={
        "your-name": "Иван Сидоров", "your-phone": "+7 913 555 00 11",
        "your-email": "ivan@mail.ru", "your-message": "Перезвоните, пожалуйста",
        "_wpcf7": "42", "_wpcf7_unit_tag": "wpcf7-f42-p7-o1",
        "page_url": "https://example.com/contacts",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "accepted" and body["lead_id"]
    assert body["delivery"] == {"sheets": "done", "telegram": "done", "email": "done"}
    lead = sinks["telegram"].sent[0]
    assert (lead.name, lead.phone, lead.email) == ("Иван Сидоров", "+79135550011", "ivan@mail.ru")
    assert lead.message == "Перезвоните, пожалуйста"
    assert lead.page == "https://example.com/contacts"
    assert lead.source == "json"
    assert lead.extra == {}  # _wpcf7* service fields are not leaked


def test_validation_errors_return_422_and_send_nothing(client, sinks, store):
    cases = [
        ({"Name": "A", "Phone": "12345"}, "phone"),
        ({"Name": "A", "Phone": "+79991234567", "Email": "not-an-email"}, "email"),
        ({"Name": "A", "Textarea": "только текст"}, "contact"),
        ({"Name": "A", "Email": "a@b..ru"}, "email"),
    ]
    for payload, field in cases:
        resp = client.post("/webhook", data=payload)
        assert resp.status_code == 422, payload
        body = resp.get_json()
        assert body["status"] == "invalid" and field in body["errors"]
    assert all(not s.sent for s in sinks.values())
    assert store.count_leads() == 0


def test_bad_bodies(client):
    assert client.post("/webhook", data="[1,2]", content_type="application/json").status_code == 400
    assert client.post("/webhook", data="x", content_type="text/plain").status_code == 415


def test_honeypot_is_accepted_silently_and_dropped(client, sinks, store):
    resp = post_tilda(client, website="http://spam.example")
    assert resp.status_code == 200 and resp.get_data(as_text=True) == "ok"  # bots learn nothing
    assert all(not s.sent for s in sinks.values())
    assert store.count_leads() == 0
    # an empty trap field (a human) passes
    assert post_tilda(client, website="", tranid="999:1").status_code == 200
    assert len(sinks["sheets"].sent) == 1


def test_json_honeypot(client, sinks):
    resp = client.post("/webhook", json={"name": "Bot", "email": "b@b.ru", "hp": "x"})
    assert resp.status_code == 200 and resp.get_json()["status"] == "spam"
    assert not sinks["sheets"].sent


def test_tilda_test_ping_returns_ok_without_fan_out(client, sinks, store):
    resp = client.post("/webhook", data={"test": "test"})
    assert resp.status_code == 200
    assert resp.get_data(as_text=True) == "ok"
    assert all(s.calls == 0 for s in sinks.values())
    assert store.count_leads() == 0


def test_secret_key_in_url(settings, sinks, store, clock, make_settings):
    from leadrouter.server import create_app

    app = create_app(make_settings(webhook_secret="s3cret"), list(sinks.values()), store, clock)
    c = app.test_client()
    assert c.post("/webhook", data=TILDA_FORM).status_code == 403
    assert c.post("/webhook?key=wrong", data=TILDA_FORM).status_code == 403
    assert c.post("/webhook?key=s3cret", data={"test": "test"}).status_code == 200
    assert c.post("/webhook?key=s3cret", data=TILDA_FORM).status_code == 200
    assert len(sinks["email"].sent) == 1


def test_health(client):
    body = client.get("/health").get_json()
    assert body["status"] == "ok" and body["sinks"] == ["email", "sheets", "telegram"]
