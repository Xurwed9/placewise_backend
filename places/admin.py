
from django.contrib import admin
from .models import Category, Brand, Place, PlacePhoto


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("slug",)


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
