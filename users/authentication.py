from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class BlockedAwareJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if not user.is_active or getattr(user, "is_blocked", False):
            raise AuthenticationFailed(
                "Ин ҳисоб дастрас нест.",
                code="USER_BLOCKED",
            )

        return user
