from __future__ import annotations

from conftest import TILDA_FORM


def post(client, **over):
    return client.post("/webhook", json={**{k.lower(): v for k, v in TILDA_FORM.items()
                                            if k not in ("tranid", "formid", "COOKIES")}, **over})


def test_same_tranid_is_a_duplicate_within_10_minutes(client, sinks, clock):
    assert client.post("/webhook", data=TILDA_FORM).status_code == 200
    clock.advance(5 * 60)
    # Tilda re-sends the same tranid, but the text changed: still the same submission
    again = client.post("/webhook", data={**TILDA_FORM, "Textarea": "другой текст"})
    assert again.status_code == 200
    assert len(sinks["sheets"].sent) == 1


def test_same_content_without_tranid_is_a_duplicate(client, sinks):
    assert post(client).get_json()["status"] == "accepted"
    assert post(client).get_json()["status"] == "duplicate"  # double click on "Send"
    # another person / another text is not a duplicate
    assert post(client, phone="8 912 000 00 00").get_json()["status"] == "accepted"
    assert len(sinks["telegram"].sent) == 2


def test_duplicate_after_window_is_accepted_again(client, sinks, clock):
    client.post("/webhook", data=TILDA_FORM)
    clock.advance(601)  # more than 10 minutes
    client.post("/webhook", data=TILDA_FORM)
    assert len(sinks["email"].sent) == 2


def test_content_hash_ignores_case_and_phone_format(client):
    assert post(client, phone="+7 (999) 123-45-67").get_json()["status"] == "accepted"
    assert post(client, phone="89991234567", name="АННА ПЕТРОВА").get_json()["status"] == "duplicate"


def test_invalid_submission_does_not_burn_the_dedupe_key(client, sinks):
    bad = client.post("/webhook", data={**TILDA_FORM, "Phone": "12"})
    assert bad.status_code == 422
    good = client.post("/webhook", data=TILDA_FORM)  # same tranid, fixed phone
    assert good.status_code == 200 and len(sinks["sheets"].sent) == 1
