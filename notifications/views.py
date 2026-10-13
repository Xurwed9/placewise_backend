
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers

from .models import Notification
from .serializers import NotificationSerializer


def active_user(request):
    return (
        request.user.is_authenticated
        and request.user.is_active
        and not getattr(request.user, "is_blocked", False)
    )


@extend_schema(
    tags=["Notifications"],
    summary="Рӯйхати огоҳиномаҳо",
    responses={
        200: inline_serializer(
            name="NotificationListResponse",
            fields={
                "unread_count": serializers.IntegerField(),
                "results": NotificationSerializer(many=True),
            },
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request):
    if not active_user(request):
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    notifications = Notification.objects.filter(
        user=request.user
    ).order_by("-created_at")

    unread_count = notifications.filter(is_read=False).count()

    return Response({
        "unread_count": unread_count,
        "results": NotificationSerializer(
            notifications[:50],
            many=True,
        ).data,
    })


@extend_schema(
    tags=["Notifications"],
    summary="Хондашуда кардани огоҳинома",
    request=None,
    responses={
        200: inline_serializer(
            name="MarkNotificationReadResponse",
            fields={
                "detail": serializers.CharField(),
                "id": serializers.IntegerField(),
                "is_read": serializers.BooleanField(),
            },
        ),
        403: inline_serializer(
            name="MarkNotificationReadForbidden",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, notification_id):
    if not active_user(request):
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])

    return Response({
        "detail": "Огоҳинома хондашуда шуд.",
        "id": notification.id,
        "is_read": notification.is_read,
    })


@extend_schema(
    tags=["Notifications"],
    summary="Хондашуда кардани ҳамаи огоҳиномаҳо",
    request=None,
    responses={
        200: inline_serializer(
            name="MarkAllNotificationsReadResponse",
            fields={
                "detail": serializers.CharField(),
                "updated_count": serializers.IntegerField(),
            },
        ),
        403: inline_serializer(
            name="MarkAllNotificationsReadForbidden",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    if not active_user(request):
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    updated_count = Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).update(is_read=True)

    return Response({
        "detail": "Ҳамаи огоҳиномаҳо хондашуда шуданд.",
        "updated_count": updated_count,
    })
