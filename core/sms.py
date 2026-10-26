import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    pass


def send_sms(phone, message):
    if not settings.SMS_ENABLED:
        logger.info("SMS disabled; message for %s not sent", phone)
        return False

    if not settings.SMS_API_URL:
        raise SMSDeliveryError("SMS_API_URL is not configured")

    payload = json.dumps({
        "phone": phone,
        "message": message,
        "sender": settings.SMS_SENDER,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "placewise-backend/1.0",
    }

    if settings.SMS_API_KEY:
        headers["Authorization"] = f"Bearer {settings.SMS_API_KEY}"

    request = Request(
        settings.SMS_API_URL,
        data=payload,
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise SMSDeliveryError(
                    f"SMS gateway returned HTTP {response.status}"
                )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SMSDeliveryError("SMS gateway request failed") from exc

    return True
