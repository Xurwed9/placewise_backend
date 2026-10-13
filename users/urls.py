from django.urls import path
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

from .views import request_code, verify_code, me

urlpatterns = [
    path("request-code/", request_code, name="request-code"),
    path("verify-code/", verify_code, name="verify-code"),
    path("me/", me, name="me"),

    path(
    "token/",
    TokenObtainPairView.as_view(),
    name="token-obtain-pair"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]