
from rest_framework.permissions import BasePermission


class IsActiveUser(BasePermission):
    """Танҳо корбари фаъол ва блокнашуда."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.is_active
            and not getattr(user, "is_blocked", False)
        )


class IsPlacewiseAdmin(BasePermission):
    """Модератор ё админи Placewise."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.is_active
            and not getattr(user, "is_blocked", False)
            and (
                user.is_superuser
                or getattr(user, "role", "") in {"moderator", "admin"}
            )
        )


class IsAdminOrSuperuser(BasePermission):
    """Танҳо админи Placewise ё superuser."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.is_active
            and not getattr(user, "is_blocked", False)
            and (
                user.is_superuser
                or getattr(user, "role", "") == "admin"
            )
        )


class IsModeratorOrAdmin(BasePermission):
    """Модератор ё админ."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.is_active
            and not getattr(user, "is_blocked", False)
            and (
                user.is_superuser
                or getattr(user, "role", "") in {
                    "moderator",
                    "admin",
                }
            )
        )


class IsOwnerOrAdmin(BasePermission):
    """Соҳиби ҷой ё админ."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user
            and user.is_authenticated
            and user.is_active
            and not getattr(user, "is_blocked", False)
            and (
                user.is_superuser
                or getattr(user, "role", "") in {
                    "owner",
                    "admin",
                }
            )
        )
