from django.contrib.auth import get_user_model

from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .phone_utils import normalize_phone
from .throttles import AdminLoginRateThrottle


User = get_user_model()


class AdminLoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(
        max_length=128,
        write_only=True,
        trim_whitespace=False,
    )

    def validate_phone(self, value):
        phone = normalize_phone(value)

        if phone is None:
            raise serializers.ValidationError(
                "Рақами телефон нодуруст аст."
            )

        return phone


class AdminLoginUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    phone = serializers.CharField()
    name = serializers.CharField(allow_blank=True)
    role = serializers.CharField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()


class AdminLoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = AdminLoginUserSerializer()


@extend_schema(
    tags=["Admin - Authentication"],
    summary="Вход администратора по телефону и паролю",
    operation_id="admin_login",
    request=AdminLoginSerializer,
    responses={
        200: AdminLoginResponseSerializer,
        400: OpenApiResponse(description="Телефон или пароль не передан."),
        401: OpenApiResponse(description="Неверный телефон или пароль."),
        403: OpenApiResponse(description="Нет доступа к админке."),
        429: OpenApiResponse(description="Слишком много попыток входа."),
    },
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AdminLoginRateThrottle])
def admin_login(request):
    serializer = AdminLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    phone = serializer.validated_data["phone"]
    password = serializer.validated_data["password"]
    raw_phone = str(request.data.get("phone", "")).strip()

    user = User.objects.filter(phone=phone).first()

    if user is None and raw_phone and raw_phone != phone:
        user = User.objects.filter(phone=raw_phone).first()

    if user is None or not user.check_password(password):
        return Response(
            {"detail": "Неверный телефон или пароль."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active or user.is_blocked:
        return Response(
            {"detail": "Этот аккаунт недоступен."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if not (
        user.is_superuser
        or user.role in {User.Role.ADMIN, User.Role.MODERATOR}
    ):
        return Response(
            {"detail": "Доступ разрешён только администраторам."},
            status=status.HTTP_403_FORBIDDEN,
        )

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.pk,
                "phone": user.phone,
                "name": user.name,
                "role": "admin" if user.is_superuser else user.role,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
            },
        },
        status=status.HTTP_200_OK,
    )
