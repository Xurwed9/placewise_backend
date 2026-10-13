
from django.urls import path

from .views import (
    notification_list,
    mark_notification_read,
    mark_all_notifications_read,
)

urlpatterns = [
    path("", notification_list, name="notification-list"),
    path(
        "read-all/",
        mark_all_notifications_read,
        name="notification-read-all",
    ),
    path(
        "<int:notification_id>/read/",
        mark_notification_read,
        name="notification-read",
    ),
]
