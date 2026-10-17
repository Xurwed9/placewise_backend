import re

from rest_framework.throttling import AnonRateThrottle


class OTPRequestRateThrottle(AnonRateThrottle):
    scope = "otp_request"

    def allow_request(self, request, view):
        phone = request.data.get("phone", "")

        # Дархости нодуруст бояд аз view ҷавоби 400 гирад.
        if not isinstance(phone, str):
            return True

        phone = re.sub(r"[\s()\-]", "", phone)

        if phone.startswith("992"):
            phone = "+" + phone
        elif phone.startswith("9") and len(phone) == 9:
            phone = "+992" + phone
        elif phone.startswith("00"):
            phone = "+" + phone[2:]

        if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
            return True

        return super().allow_request(request, view)
