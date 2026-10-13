
from django.contrib import admin

from .models import Category, Brand, Place, PlacePhoto, Claim


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "key",
        "slug",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active",)
    search_fields = ("slug", "key")
    list_editable = ("is_active", "sort_order")


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "branches_count")
    search_fields = ("slug",)


class PlacePhotoInline(admin.TabularInline):
    model = PlacePhoto
    extra = 1


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "slug",
        "category",
        "status",
        "rating",
        "reviews_count",
    )
    list_filter = ("status", "category", "district")
    search_fields = ("slug", "district")
    inlines = [PlacePhotoInline]


@admin.register(PlacePhoto)
class PlacePhotoAdmin(admin.ModelAdmin):
    list_display = ("id", "place", "is_cover", "sort_order")
    list_filter = ("is_cover",)



@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "place",
        "user",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("place__slug", "user__phone")
    readonly_fields = ("created_at",)
    