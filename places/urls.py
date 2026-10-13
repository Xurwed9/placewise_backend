from django.urls import path

from .views import (
    category_list,
    place_list,
    place_detail,
    place_map,
    similar_places,
    favorite_list,
    favorite_delete,home,
    search_suggest, owner_place_update, owner_places,
    owner_review_reply,
    claim_create, admin_claim_list, admin_claim_review,
    upload_image, admin_place_publish, admin_place_hide,
    admin_places_list,admin_place_update,
)

urlpatterns = [
    path("categories/", category_list, name="category-list"),

    path("places/", place_list, name="place-list"),
    path("places/map/", place_map, name="place-map"),
    path(
        "places/<slug:slug>/similar/",
        similar_places,
        name="similar-places",
    ),
    path("places/<slug:slug>/", place_detail, name="place-detail"),

    path("favorites/", favorite_list, name="favorite-list"),
    path(
        "favorites/<int:place_id>/",
        favorite_delete,
        name="favorite-delete",
    ),
    path("home/", home, name="home"),
    path(
    "search/suggest/",
    search_suggest,
    name="search-suggest",
    ),
    path("owner/places/", owner_places, name="owner-places"),
    path(
    "owner/places/<int:place_id>/",
    owner_place_update,
    name="owner-place-update",
    ),
    path(
    "owner/reviews/<int:review_id>/reply/",
    owner_review_reply,
    name="owner-review-reply", ),
    path("claims/", claim_create, name="claim-create"),
    path("admin/claims/", admin_claim_list, name="admin-claim-list"),
    path(
    "admin/claims/<int:claim_id>/",
    admin_claim_review,
    name="admin-claim-review",),
    path("uploads/", upload_image, name="upload-image"),
    path(
    "admin/places/<int:place_id>/publish/",
    admin_place_publish,
    name="admin-place-publish"),
    path(
    "admin/places/<int:place_id>/hide/",
    admin_place_hide,
    name="admin-place-hide"),
    path(
    "admin/places/",
    admin_places_list,
    name="admin-places-list"),
    path(
    "admin/places/<int:place_id>/",
    admin_place_update,
    name="admin-place-update"),

]
