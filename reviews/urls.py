from django.urls import path

from .views import place_reviews


urlpatterns = [
    path(
        "places/<slug:slug>/reviews/",
        place_reviews,
        name="place-reviews",
    ),
]
