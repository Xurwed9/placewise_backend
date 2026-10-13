
from django.urls import path

from .views import (
    place_reviews,
    review_detail,
    review_like,
    review_report,
    moderation_queue,
    moderate_review,review_photo_upload,
    moderation_reports, resolve_report,
)

urlpatterns = [
    path(
        "places/<slug:slug>/reviews/",
        place_reviews,
        name="place-reviews",
    ),
    path(
        "reviews/<int:review_id>/",
        review_detail,
        name="review-detail",
    ),
    path(
        "reviews/<int:review_id>/like/",
        review_like,
        name="review-like",
    ),
    path(
        "reviews/<int:review_id>/report/",
        review_report,
        name="review-report",
    ),
    path(
    "moderation/reviews/",
    moderation_queue,
    name="moderation-queue",
    ),  
    path(
        "moderation/reviews/<int:review_id>/",
        moderate_review,
        name="moderate-review",),
    path(
    "reviews/<int:review_id>/photos",
    review_photo_upload,
    name="review-photo-upload"),
    path(
    "admin/reports",
    moderation_reports,
    name="moderation-reports"),
    path(
    "admin/reports/<int:report_id>/resolve",
    resolve_report,
    name="resolve-report"),
]
