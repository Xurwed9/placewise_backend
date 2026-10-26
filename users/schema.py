from drf_spectacular.extensions import OpenApiAuthenticationExtension


class BlockedAwareJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "users.authentication.BlockedAwareJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
