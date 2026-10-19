"""Turn a raw form payload (Tilda / WordPress / custom) into a validated Lead."""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

# Canonical field -> accepted input names (compared case-insensitively).
ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "your-name", "fio", "full_name", "fullname", "username", "имя"),
    "phone": ("phone", "your-phone", "tel", "telephone", "mobile", "телефон"),
    "email": ("email", "e-mail", "your-email", "mail", "почта"),
    "message": ("message", "your-message", "comment", "comments", "textarea", "text",
                "question", "сообщение", "комментарий"),
    "form": ("formname", "form_name", "form_id", "formid", "form"),
    "page": ("page_url", "page", "referer", "referrer"),
}
# Technical fields that are never copied into "extra".
SERVICE_FIELDS = {"tranid", "formid", "formname", "cookies", "test", "g-recaptcha-response",
                  "h-captcha-response", "cf-turnstile-response", "key"}
SERVICE_PREFIXES = ("_wpcf7", "_wpnonce", "_wp_http_referer")

LIMITS = {"name": 120, "phone": 40, "email": 254, "message": 5000, "form": 120, "page": 500}
EXTRA_LIMIT = 500
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-']+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}$")


class ValidationError(Exception):
    def __init__(self, errors: dict[str, str]):
        super().__init__(errors)
        self.errors = errors


@dataclass
class Lead:
    id: str
    created_at: str  # ISO 8601, UTC
    name: str = ""
    phone: str = ""
    email: str = ""
    message: str = ""
    source: str = "form"  # tilda | form | json
    form: str = ""
    page: str = ""
    tranid: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    def content_hash(self) -> str:
        raw = "|".join(s.casefold() for s in (self.name, self.phone, self.email, self.message))
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def dedupe_keys(self) -> list[str]:
        keys = ["h:" + self.content_hash()]
        if self.tranid:
            keys.insert(0, "t:" + self.tranid)
        return keys


def clean_text(value: Any, limit: int = 300, multiline: bool = False) -> str:
    """Stringify, drop control characters, trim, cap. Single-line unless `multiline`
    (line breaks never reach email headers: a name cannot inject a Bcc line)."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    elif isinstance(value, bool):
        value = "да" if value else "нет"
    elif isinstance(value, (dict, set)):
        value = str(value)
    text = _CTRL.sub(" ", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip()[:limit]


def normalize_phone(raw: str) -> str:
    """Return +7XXXXXXXXXX for Russian numbers, +<digits> for other international ones.

    Raises ValueError for anything that is not a plausible phone number.
    """
    text = re.split(r"(?i)\b(?:доб|ext)\b|#", raw, maxsplit=1)[0]
    digits = re.sub(r"\D", "", text)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10 and digits[0] in "3489":
        return "+7" + digits
    if text.strip().startswith("+") and 8 <= len(digits) <= 15 and not digits.startswith("7"):
        return "+" + digits
    raise ValueError("bad phone")


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if len(email) > 254 or ".." in email or not _EMAIL.match(email):
        raise ValueError("bad email")
    return email


def is_honeypot_hit(raw: Mapping[str, Any], honeypot_fields: tuple[str, ...]) -> bool:
    traps = {f.lower() for f in honeypot_fields}
    return any(str(k).lower() in traps and clean_text(v) for k, v in raw.items())


def detect_source(raw: Mapping[str, Any], is_json: bool) -> str:
    keys = {str(k).lower() for k in raw}
    if "tranid" in keys:
        return "tilda"
    return "json" if is_json else "form"


def build_lead(raw: Mapping[str, Any], source: str, now: float,
               honeypot_fields: tuple[str, ...] = ()) -> Lead:
    lowered = {str(k).strip().lower(): v for k, v in raw.items()}
    used: set[str] = set()

    def pick(canonical: str) -> str:
        multiline = canonical == "message"
        for alias in ALIASES[canonical]:
            value = clean_text(lowered.get(alias), LIMITS[canonical], multiline)
            if value:
                used.add(alias)
                return value
        return ""

    values = {c: pick(c) for c in ALIASES}
    errors: dict[str, str] = {}

    phone = ""
    if values["phone"]:
        try:
            phone = normalize_phone(values["phone"])
        except ValueError:
            errors["phone"] = "Некорректный телефон"
    email = ""
    if values["email"]:
        try:
            email = normalize_email(values["email"])
        except ValueError:
            errors["email"] = "Некорректный email"
    if not errors and not (phone or email):
        errors["contact"] = "Укажите телефон или email"
    if errors:
        raise ValidationError(errors)

    skip = used | SERVICE_FIELDS | {h.lower() for h in honeypot_fields}
    extra = {}
    for original, value in raw.items():
        key = str(original).strip().lower()
        if key in skip or key.startswith(SERVICE_PREFIXES):
            continue
        text = clean_text(value, EXTRA_LIMIT)
        if text:
            extra[clean_text(original, 60)] = text  # keeps the visitor-facing spelling

    return Lead(
        id=uuid.uuid4().hex,
        created_at=datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="seconds"),
        name=values["name"], phone=phone, email=email, message=values["message"],
        source=source, form=values["form"], page=values["page"],
        tranid=clean_text(lowered.get("tranid"), 100), extra=extra,
    )
