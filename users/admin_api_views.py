from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from core.pagination import StandardPagination
from rest_framework.response import Response

from users.permissions import IsAdminOrSuperuser, IsPlacewiseAdmin
from users.serializers import AdminUserSerializer
from users.phone_utils import normalize_phone
from rest_framework import serializers, status
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
    inline_serializer,
)


User = get_user_model()


class AdminUserCreateSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=False,
        write_only=True,
    )
    name = serializers.CharField(
        max_length=150, required=False, allow_blank=True
    )
    role = serializers.ChoiceField(
        choices=[
            ("user", "Корбари оддӣ"),
            ("owner", "Соҳиби ҷой"),
            ("moderator", "Модератор"),
            ("admin", "Админ"),
        ],
        default=User.Role.USER,
    )
    language = serializers.ChoiceField(
        choices=["ru", "tg", "en"], default="ru"
    )
    lang = serializers.ChoiceField(
        choices=["ru", "tg", "en"],
        required=False,
    )

    def validate_phone(self, value):
        value = normalize_phone(value)
        if not value:
            raise serializers.ValidationError(
                "Рақами телефон нодуруст аст."
            )
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError(
                "Ин рақами телефон аллакай сабт шудааст."
            )
        return value

    def validate_role(self, value):
        request = self.context.get("request")
        if value == "admin" and not (
            request and request.user.is_superuser
        ):
            raise serializers.ValidationError(
                "Танҳо superuser метавонад нақши admin диҳад."
            )
        return value

    def validate_password(self, value):
        candidate = User(
            username=self.initial_data.get("phone", ""),
            phone=self.initial_data.get("phone", ""),
            name=self.initial_data.get("name", ""),
        )
        try:
            validate_password(value, user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        if (
            attrs.get("role") in {"admin", "moderator"}
            and not attrs.get("password")
        ):
            raise serializers.ValidationError({
                "password": (
                    "Для роли admin или moderator пароль обязателен."
                )
            })

        return attrs

    def create(self, validated_data):
        role = validated_data["role"]
        phone = validated_data["phone"]
        password = validated_data.pop("password", None)

        user = User(
            username=phone,
            phone=phone,
            name=validated_data.get("name", ""),
            language=(
                validated_data.get("lang")
                or validated_data.get("language", "ru")
            ),
            role=role,
            is_staff=role in {"moderator", "admin"},
            is_active=True,
            is_blocked=False,
            is_superuser=False,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user


class AdminUserSetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        max_length=128,
        write_only=True,
        trim_whitespace=False,
    )

    def validate_new_password(self, value):
        target_user = self.context.get("user")

        try:
            validate_password(value, user=target_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc

        return value


@extend_schema(
    methods=["GET"],
    tags=["Admin - Users"],
    summary="Рӯйхати корбарон",
    operation_id="admin_users_list",
    parameters=[
        OpenApiParameter("search", str, description="Ҷустуҷӯ аз рӯйи телефон, ном ё username"),
        OpenApiParameter("role", str, description="Филтр аз рӯйи нақш"),
        OpenApiParameter("is_blocked", str, enum=["true", "false"]),
        OpenApiParameter("is_active", str, enum=["true", "false"]),
        OpenApiParameter("page", int),
        OpenApiParameter("limit", int),
        OpenApiParameter("page_size", int),
    ],
    responses=inline_serializer(
        name="AdminUserPaginatedResponse",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": AdminUserSerializer(many=True),
            "items": AdminUserSerializer(many=True),
            "total": serializers.IntegerField(),
            "page": serializers.IntegerField(),
            "limit": serializers.IntegerField(),
        },
    ),
)
@extend_schema(
    methods=["POST"],
    tags=["Admin - Users"],
    summary="Сохтани корбари нав",
    operation_id="admin_user_create",
    request=AdminUserCreateSerializer,
    responses={201: AdminUserSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_users_list(request):
    if request.method == "POST":
        create_serializer = AdminUserCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        create_serializer.is_valid(raise_exception=True)
        user = create_serializer.save()
        return Response(
            AdminUserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )

    users = User.objects.all().order_by("-date_joined")

    search = request.query_params.get("search", "").strip()
    role = request.query_params.get("role", "").strip()
    blocked = request.query_params.get("is_blocked")
    active = request.query_params.get("is_active")

    if search:
        users = users.filter(
            Q(phone__icontains=search)
            | Q(name__icontains=search)
            | Q(username__icontains=search)
        )

    if role:
        users = users.filter(role=role)

    if blocked in {"true", "false"}:
        users = users.filter(is_blocked=(blocked == "true"))

    if active in {"true", "false"}:
        users = users.filter(is_active=(active == "true"))

    paginator = StandardPagination()
    page = paginator.paginate_queryset(users, request)

    serializer = AdminUserSerializer(
        page,
        many=True,
        context={"request": request},
    )

    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    methods=["GET"],
    tags=["Admin - Users"],
    summary="Гирифтани маълумоти корбар",
    operation_id="admin_user_detail_retrieve",
    responses=AdminUserSerializer,
)
@extend_schema(
    methods=["PATCH"],
    tags=["Admin - Users"],
    summary="Тағйир додани маълумоти корбар",
    operation_id="admin_user_detail_update",
    request=AdminUserSerializer,
    responses=AdminUserSerializer,
)
@api_view(["GET", "PATCH"])
@permission_classes([IsPlacewiseAdmin])
def admin_user_detail(request, user_id):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "Корбар ёфт нашуд."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = AdminUserSerializer(
            user,
            context={"request": request},
        )
        return Response(serializer.data)

    # Ҳисоби худашро аз блок ё ғайрифаъол карда натавонад.
    protected_fields = {"is_blocked", "is_active", "role"}

    if user.pk == request.user.pk and protected_fields.intersection(
        request.data.keys()
    ):
        return Response(
            {"detail": "Шумо наметавонед нақш ё ҳолати ҳисоби худро тағйир диҳед."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Админи оддӣ наметавонад ҳисоби superuser-ро идора кунад.
    if (
    user.is_superuser or user.role == "admin"
    ) and not request.user.is_superuser:
        return Response(
            {"detail": "Идоракунии ин ҳисоб танҳо барои superuser иҷозат аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = AdminUserSerializer(
        user,
        data=request.data,
        partial=True,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    # Админи оддӣ наметавонад корбари дигарро admin таъин кунад.
    if (
        serializer.validated_data.get("role") == "admin"
        and not request.user.is_superuser
    ):
        return Response(
            {"detail": "Танҳо superuser метавонад нақши admin диҳад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer.save()
    return Response(serializer.data)


@extend_schema(
    tags=["Admin - Users"],
    summary="Изменение пароля пользователя",
    operation_id="admin_user_set_password",
    request=AdminUserSetPasswordSerializer,
    responses={
        204: OpenApiResponse(description="Пароль изменён."),
        400: OpenApiResponse(description="Некорректный пароль."),
        403: OpenApiResponse(description="Недостаточно прав."),
        404: OpenApiResponse(description="Пользователь не найден."),
    },
)
@api_view(["POST"])
@permission_classes([IsAdminOrSuperuser])
def admin_user_set_password(request, user_id):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "Корбар ёфт нашуд."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if (
        user.is_superuser or user.role == User.Role.ADMIN
    ) and not request.user.is_superuser:
        return Response(
            {"detail": "Танҳо superuser метавонад пароли админро тағйир диҳад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = AdminUserSetPasswordSerializer(
        data=request.data,
        context={"user": user},
    )
    serializer.is_valid(raise_exception=True)

    user.set_password(serializer.validated_data["new_password"])
    user.save(update_fields=["password"])

    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["Admin - Users"],
    summary="Блок кардани корбар",
    operation_id="admin_user_block",
    request=None,
    responses=inline_serializer(
        name="AdminUserBlockResponse",
        fields={
            "id": serializers.IntegerField(),
            "phone": serializers.CharField(),
            "is_blocked": serializers.BooleanField(),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_user_block(request, user_id):
    return _set_user_block_status(
        request,
        user_id,
        blocked=True,
    )


@extend_schema(
    tags=["Admin - Users"],
    summary="Баровардани корбар аз блок",
    operation_id="admin_user_unblock",
    request=None,
    responses=inline_serializer(
        name="AdminUserUnblockResponse",
        fields={
            "id": serializers.IntegerField(),
            "phone": serializers.CharField(),
            "is_blocked": serializers.BooleanField(),
            "detail": serializers.CharField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_user_unblock(request, user_id):
    return _set_user_block_status(
        request,
        user_id,
        blocked=False,
    )


def _set_user_block_status(request, user_id, blocked):
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response(
            {"detail": "Корбар ёфт нашуд."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if user.pk == request.user.pk:
        return Response(
            {"detail": "Шумо наметавонед ҳисоби худро блок ё разблок кунед."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if (
    user.is_superuser or user.role == "admin"
) and not request.user.is_superuser:
        return Response(
            {"detail": "Идоракунии ин ҳисоб танҳо барои superuser иҷозат аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    user.is_blocked = blocked
    user.save(update_fields=["is_blocked"])

    return Response(
        {
            "id": user.id,
            "phone": user.phone,
            "is_blocked": user.is_blocked,
            "detail": (
                "Корбар блок карда шуд."
                if blocked
                else "Блоки корбар бардошта шуд."
            ),
        },
        status=status.HTTP_200_OK,
    )