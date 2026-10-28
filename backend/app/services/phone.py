import phonenumbers

from app.config import get_settings
from app.errors import ValidationFailed


def normalize_phone(raw: str) -> str:
    """Проверяет номер и приводит к международному формату E.164 (+79991234567)."""
    raw = (raw or "").strip()
    if not raw:
        raise ValidationFailed("Укажите номер телефона", code="phone_required")
    try:
        num = phonenumbers.parse(raw, get_settings().default_phone_region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationFailed("Некорректный номер телефона", code="invalid_phone") from exc
    if not phonenumbers.is_valid_number(num):
        raise ValidationFailed("Некорректный номер телефона", code="invalid_phone")
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
