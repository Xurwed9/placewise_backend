from django.urls import re_path

from users.admin_api_views import (
    admin_users_list,
    admin_user_detail,
    admin_user_set_password,
    admin_user_block,
    admin_user_unblock,
)

urlpatterns = [
    re_path(r"^$", admin_users_list, name="admin-users-list"),
    re_path(
        r"^(?P<user_id>\d+)/?$",
        admin_user_detail,
        name="admin-user-detail",
    ),
    re_path(
        r"^(?P<user_id>\d+)/set-password/?$",
        admin_user_set_password,
        name="admin-user-set-password",
    ),
    re_path(
        r"^(?P<user_id>\d+)/block/?$",
        admin_user_block,
        name="admin-user-block",
    ),
    re_path(
        r"^(?P<user_id>\d+)/unblock/?$",
        admin_user_unblock,
        name="admin-user-unblock",
    ),
]
