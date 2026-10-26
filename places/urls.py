from django.urls import re_path

from .import_views import admin_import_2gis
from .views import (
    category_list,
    place_list,
    place_detail,
    place_map,
    similar_places,
    home,
    me_favorite_list,
    search_suggest,
    owner_place_update,
    owner_places,
    owner_review_reply,
    claim_create,
    admin_claim_list,
    upload_image,
    admin_place_publish,
    admin_place_hide,
    owner_place_photos,
    owner_photo_detail,
    admin_places_list,
    admin_place_update,
    admin_categories,
    admin_category_detail,
    admin_place_photos,
    admin_photo_detail,
)

urlpatterns = [
    re_path(r"^categories/?$", category_list, name="category-list"),
    re_path(r"^places/?$", place_list, name="place-list"),
    re_path(r"^places/map/?$", place_map, name="place-map"),
    re_path(
        r"^places/(?P<slug>[-a-zA-Z0-9_]+)/similar/?$",
        similar_places,
        name="similar-places",
    ),
    re_path(
        r"^places/(?P<slug>[-a-zA-Z0-9_]+)/claim/?$",
        claim_create,
        name="place-claim",
    ),
    re_path(
        r"^places/(?P<slug>[-a-zA-Z0-9_]+)/?$",
        place_detail,
        name="place-detail",
    ),
    re_path(
        r"^me/favorites/?$",
        me_favorite_list,
        name="me-favorite-list",
    ),
    re_path(r"^home/?$", home, name="home"),
    re_path(r"^search/suggest/?$", search_suggest, name="search-suggest"),
    re_path(r"^owner/places/?$", owner_places, name="owner-places"),
    re_path(
        r"^owner/places/(?P<place_id>\d+)/?$",
        owner_place_update,
        name="owner-place-update",
    ),
    re_path(
        r"^owner/places/(?P<place_id>\d+)/photos/?$",
        owner_place_photos,
        name="owner-place-photos",
    ),
    re_path(
    r"^owner/places/(?P<place_id>\d+)/photos/(?P<photo_id>\d+)/?$",
    owner_photo_detail,
    name="owner-photo-detail",
    ),
    re_path(
        r"^owner/reviews/(?P<review_id>\d+)/reply/?$",
        owner_review_reply,
        name="owner-review-reply",
    ),
    re_path(r"^admin/claims/?$", admin_claim_list, name="admin-claim-list"),
    re_path(r"^uploads/?$", upload_image, name="upload-image"),
    re_path(
        r"^admin/places/?$",
        admin_places_list,
        name="admin-places-list",
    ),
    re_path(
        r"^admin/places/(?P<place_id>\d+)/?$",
        admin_place_update,
        name="admin-place-update",
    ),
    re_path(
        r"^admin/places/(?P<place_id>\d+)/publish/?$",
        admin_place_publish,
        name="admin-place-publish",
    ),
    re_path(
        r"^admin/places/(?P<place_id>\d+)/hide/?$",
        admin_place_hide,
        name="admin-place-hide",
    ),
    re_path(
        r"^admin/places/(?P<place_id>\d+)/photos/?$",
        admin_place_photos,
        name="admin-place-photos",
    ),
    re_path(
        r"^admin/photos/(?P<photo_id>\d+)/?$",
        admin_photo_detail,
        name="admin-photo-detail",
    ),
    re_path(r"^admin/categories/?$", admin_categories, name="admin-categories"),
    re_path(
        r"^admin/categories/(?P<category_id>\d+)/?$",
        admin_category_detail,
        name="admin-category-detail",
    ),
    re_path(
        r"^admin/import/2gis/?$",
        admin_import_2gis,
        name="admin-import-2gis",
    ),
]
