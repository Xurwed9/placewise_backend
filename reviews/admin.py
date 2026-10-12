
from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "place",
        "rating",
        "status",
        "created_at",
    )

    list_filter = ("status", "rating", "created_at")

    search_fields = (
        "user__phone",
        "user__name",
        "place__name",
        "text",
    )

    readonly_fields = ("created_at", "updated_at")

    list_editable = ("status",)

    ordering = ("-created_at",)
