from rest_framework.throttling import SimpleRateThrottle

from .phone_utils import normalize_phone


class OTPRequestRateThrottle(SimpleRateThrottle):
    scope = "otp_request"

    def get_cache_key(self, request, view):
        phone = normalize_phone(request.data.get("phone", ""))

        if phone is None:
            return None

        return self.cache_format % {
            "scope": self.scope,
            "ident": phone,
        }


class AdminLoginRateThrottle(SimpleRateThrottle):
    scope = "admin_login"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
