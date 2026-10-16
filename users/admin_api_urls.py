from django.urls import path

from users.admin_api_views import (
    admin_users_list,
    admin_user_detail,
    admin_user_block,
    admin_user_unblock,
)

urlpatterns = [
    path("", admin_users_list, name="admin-users-list"),
    path("<int:user_id>/", admin_user_detail, name="admin-user-detail"),
    path(
        "<int:user_id>/block/",
        admin_user_block,
        name="admin-user-block",
    ),
    path(
        "<int:user_id>/unblock/",
        admin_user_unblock,
        name="admin-user-unblock",
    ),
]