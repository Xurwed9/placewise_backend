import re


def normalize_phone(phone):
    phone = re.sub(r"[\s()\-]", "", phone or "")

    if phone.startswith("992"):
        phone = "+" + phone
    elif phone.startswith("9") and len(phone) == 9:
        phone = "+992" + phone
    elif phone.startswith("00"):
        phone = "+" + phone[2:]

    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
        return None

    return phone
