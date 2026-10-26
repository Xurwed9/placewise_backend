from django.urls import path, re_path
from .admin_auth import admin_login
from rest_framework_simplejwt.views import TokenRefreshView

from .views import request_code, verify_code

urlpatterns = [
    re_path(r"^send-code/?$", request_code, name="send-code"),
    re_path(r"^verify/?$", verify_code, name="verify"),
    re_path(
        r"^refresh/?$",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),
    path(
        "admin/login/",
        admin_login,
        name="admin-login",
    ),
]
