
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


def active_user(request):
    return (
        request.user.is_authenticated
        and request.user.is_active
        and not getattr(request.user, "is_blocked", False)
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
