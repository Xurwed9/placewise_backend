
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, PhoneOTP


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "id",
        "phone",
        "name",
        "role",
        "is_blocked",
        "is_active",
        "is_staff",
    )
    list_filter = (
        "role",
        "is_blocked",
        "is_active",
        "is_staff",
    )
    search_fields = ("phone", "name", "username")
    ordering = ("-date_joined",)

    fieldsets = UserAdmin.fieldsets + (
        (
            "Placewise",
            {
                "fields": (
                    "phone",
                    "name",
                    "avatar",
                    "language",
                    "role",
                    "is_blocked",
                )
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Placewise",
            {
                "fields": (
                    "phone",
                    "name",
                    "language",
                    "role",
                )
            },
        ),
    )


@admin.register(PhoneOTP)
class PhoneOTPAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "phone",
        "created_at",
        "expires_at",
        "attempts",
        "consumed_at",
    )
    search_fields = ("phone",)
    list_filter = ("created_at", "consumed_at")
    readonly_fields = (
        "phone",
        "code_hash",
        "created_at",
        "expires_at",
        "attempts",
        "consumed_at",
    )
