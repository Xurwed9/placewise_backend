"""Custom OpenAPI schema helpers for the Placewise API.

The project exposes a fairly large public + owner + admin API surface.  Most
views are plain function based views, so drf-spectacular would otherwise put
everything into a single generic "v1" tag.  This module derives a stable,
human friendly tag (and a short summary when the view does not provide one)
from the request path and method.
"""

from __future__ import annotations

from typing import Optional

from drf_spectacular.openapi import AutoSchema


ADMIN_TAGS = {
    "categories": "Admin - Categories",
    "claims": "Admin - Claims",
    "import": "Admin - Imports",
    "photos": "Admin - Places",
    "places": "Admin - Places",
    "reports": "Admin - Reports",
    "reviews": "Admin - Reviews",
    "users": "Admin - Users",
}


def resolve_tag(path: str) -> str:
    """Return the Swagger tag responsible for a given API path."""

    clean_path = path.rstrip("/") or "/"

    if clean_path.startswith("/api/v1/admin/"):
        section = clean_path[len("/api/v1/admin/"):].split("/", 1)[0]
        return ADMIN_TAGS.get(section, "Admin")

    if clean_path.startswith("/api/v1/auth/admin/"):
        return "Admin - Authentication"

    if clean_path.startswith("/api/v1/owner/"):
        section = clean_path[len("/api/v1/owner/"):]
        if section.startswith("photos/"):
            return "Owner - Photos"
        if section.startswith("places/") and "/photos" in section:
            return "Owner - Photos"
        if section.startswith("reviews/"):
            return "Owner - Reviews"
        return "Owner - Places"

    if clean_path == "/api/v1/me":
        return "Profile"

    if clean_path.startswith("/api/v1/me/favorites"):
        return "Favorites"

    if clean_path.startswith("/api/v1/auth/"):
        return "Authentication"

    if clean_path.startswith("/api/v1/auth"):
        return "Authentication"

    if clean_path.startswith("/api/v1/notifications"):
        return "Notifications"

    if clean_path.startswith("/api/v1/categories"):
        return "Categories"

    if clean_path.startswith("/api/v1/home") or clean_path.startswith("/api/v1/search"):
        return "Search & Home"

    if "/claim" in clean_path:
        return "Claims"

    if clean_path.startswith("/api/v1/reviews") or "/reviews" in clean_path:
        return "Reviews"

    if clean_path.startswith("/api/v1/places"):
        return "Places"

    if clean_path.startswith("/api/v1/uploads"):
        return "Uploads"

    return "Other"


OPERATION_SUMMARIES = {
    ("GET", "/api/v1/admin/categories/"): "Рӯйхати категорияҳо (админ)",
    ("POST", "/api/v1/admin/categories/"): "Сохтани категория",
    ("GET", "/api/v1/admin/categories/{category_id}/"): "Маълумоти категория (админ)",
    ("PATCH", "/api/v1/admin/categories/{category_id}/"): "Таҳрири категория",
    ("DELETE", "/api/v1/admin/categories/{category_id}/"): "Нест кардани категория",
    ("PATCH", "/api/v1/admin/photos/{photo_id}/"): "Таҳрири акси ҷой",
    ("DELETE", "/api/v1/admin/photos/{photo_id}/"): "Нест кардани акси ҷой",
    ("GET", "/api/v1/admin/places/"): "Рӯйхати ҷойҳо (админ)",
    ("POST", "/api/v1/admin/places/"): "Сохтани ҷой",
    ("GET", "/api/v1/admin/places/{place_id}/"): "Маълумоти ҷой (админ)",
    ("PATCH", "/api/v1/admin/places/{place_id}/"): "Таҳрири ҷой (админ)",
    ("DELETE", "/api/v1/admin/places/{place_id}/"): "Нест кардани ҷой",
    ("GET", "/api/v1/admin/places/{place_id}/photos/"): "Рӯйхати аксҳои ҷой (админ)",
    ("POST", "/api/v1/admin/places/{place_id}/photos/"): "Илова кардани акс ба ҷой (админ)",
    ("GET", "/api/v1/admin/reviews/"): "Рӯйхати отзывҳо барои модератор",
    ("POST", "/api/v1/auth/refresh/"): "Навсозии access token",
    ("POST", "/api/v1/auth/send-code/"): "Дархости коди тасдиқ",
    ("POST", "/api/v1/auth/verify/"): "Тасдиқи коди воридшавӣ",
    ("GET", "/api/v1/categories/"): "Рӯйхати категорияҳо",
    ("GET", "/api/v1/me/"): "Маълумоти профили корбар",
    ("PATCH", "/api/v1/me/"): "Таҳрири профили корбар",
    ("GET", "/api/v1/me/favorites/"): "Рӯйхати ҷойҳои дӯстдошта",
    ("POST", "/api/v1/me/favorites/"): "Илова кардан ба дӯстдоштаҳо",
    ("DELETE", "/api/v1/me/favorites/"): "Нест кардан аз дӯстдоштаҳо",
    ("PATCH", "/api/v1/owner/photos/{photo_id}/"): "Таҳрири акси ҷой",
    ("DELETE", "/api/v1/owner/photos/{photo_id}/"): "Нест кардани акси ҷой",
    ("GET", "/api/v1/owner/places/{place_id}/photos/"): "Рӯйхати аксҳои ҷой",
    ("POST", "/api/v1/owner/places/{place_id}/photos/"): "Илова кардани акс ба ҷой",
    ("GET", "/api/v1/places/"): "Рӯйхати ҷойҳо",
    ("GET", "/api/v1/places/{slug}/"): "Маълумоти ҷой",
    ("GET", "/api/v1/places/{slug}/similar/"): "Ҷойҳои монанд",
    ("GET", "/api/v1/places/map/"): "Ҷойҳо дар харита",
    ("GET", "/api/v1/places/{slug}/reviews/"): "Рӯйхати отзывҳои ҷой",
    ("POST", "/api/v1/places/{slug}/reviews/"): "Сохтани отзыв",
    ("PATCH", "/api/v1/reviews/{review_id}/"): "Таҳрири отзыв",
    ("DELETE", "/api/v1/reviews/{review_id}/"): "Нест кардани отзыв",
    ("POST", "/api/v1/reviews/{review_id}/like/"): "Лайк кардани отзыв",
    ("DELETE", "/api/v1/reviews/{review_id}/like/"): "Бекор кардани лайк",
    ("POST", "/api/v1/reviews/{review_id}/report/"): "Шикоят аз отзыв",
    ("GET", "/api/v1/search/suggest/"): "Пешниҳодҳои ҷустуҷӯ",
}


class PlacewiseAutoSchema(AutoSchema):
    """AutoSchema with project-wide tag/summary rules."""

    def get_tags(self) -> list[str]:
        return [resolve_tag(self.path)]

    def get_summary(self) -> Optional[str]:
        summary = OPERATION_SUMMARIES.get((self.method, self.path))
        if summary:
            return summary
        return super().get_summary()
