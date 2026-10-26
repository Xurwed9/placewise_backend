import re

URL_PATTERN = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|instagram\.com/|wa\.me/)",
    re.IGNORECASE,
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?992|8)?[\s\-()]*\d(?:[\s\-()]*\d){7,}(?!\d)"
)

PROFANITY_PATTERN = re.compile(
    r"(?<!\w)(?:"
    r"ху[йя]|хуел|пизд|бляд|ебат|ебал|ебан|мудак|мудил|"
    r"сука|нахуй|залуп|гандон|долбо[её]б|"
    r"ахмоқ|аблаҳ|ҳаром|қаҳба|фоҳиша|супор|"
    r"fuck|shit|bitch|asshole"
    r")(?!\w)",
    re.IGNORECASE,
)

REJECTION_MESSAGES = {
    "LINKS_NOT_ALLOWED": {
        "ru": "Ссылки в отзывах запрещены.",
        "tg": "Истинодҳо дар отзывҳо манъанд.",
        "en": "Links are not allowed in reviews.",
    },
    "PHONE_NOT_ALLOWED": {
        "ru": "Номера телефонов в отзывах запрещены.",
        "tg": "Рақамҳои телефон дар отзывҳо манъанд.",
        "en": "Phone numbers are not allowed in reviews.",
    },
    "PROFANITY": {
        "ru": "Отзыв содержит недопустимые выражения.",
        "tg": "Отзыв ибораҳои ноқобил дорад.",
        "en": "The review contains prohibited language.",
    },
}


def review_auto_reject_reason(text):
    if URL_PATTERN.search(text):
        return "LINKS_NOT_ALLOWED"

    if PHONE_PATTERN.search(text):
        return "PHONE_NOT_ALLOWED"

    if PROFANITY_PATTERN.search(text):
        return "PROFANITY"

    return None


def rejection_message(reason, language="ru"):
    messages = REJECTION_MESSAGES.get(reason)
    if messages is None:
        return ""

    return messages.get(language, messages["ru"])
