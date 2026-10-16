from django.contrib.auth import get_user_model
from django.db.models import Q

from rest_framework.decorators import (
    api_view,
    permission_classes,
)
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from users.permissions import IsPlacewiseAdmin
from users.serializers import AdminUserSerializer
from rest_framework import serializers, status
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    inline_serializer,
)


User = get_user_model()


@extend_schema(
    tags=["Admin - Users"],
    summary="Рӯйхати корбарон",
    operation_id="admin_users_list",
    parameters=[
        OpenApiParameter("search", str, description="Ҷустуҷӯ аз рӯйи телефон, ном ё username"),
        OpenApiParameter("role", str, description="Филтр аз рӯйи нақш"),
        OpenApiParameter("is_blocked", str, enum=["true", "false"]),
        OpenApiParameter("is_active", str, enum=["true", "false"]),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int),
    ],
    responses=inline_serializer(
        name="AdminUserPaginatedResponse",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(allow_null=True),
            "previous": serializers.URLField(allow_null=True),
            "results": AdminUserSerializer(many=True),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsPlacewiseAdmin])
def admin_users_list(request):
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

    paginator = PageNumberPagination()
    paginator.page_size = 20
    paginator.page_size_query_param = "page_size"
    paginator.max_page_size = 100

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