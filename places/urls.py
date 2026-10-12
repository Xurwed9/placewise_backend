from django.urls import path

from .views import (
    category_list,
    place_list,
    place_detail,
    place_map,
    similar_places,
    favorite_list,
    favorite_delete,
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
]
