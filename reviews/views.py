
from django.shortcuts import get_object_or_404
from io import BytesIO
from PIL import Image
from rest_framework.decorators import (
    api_view,
    permission_classes,
    parser_classes,
)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from datetime import timedelta
from django.utils import timezone

from .models import Review, ReviewPhoto

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.decorators import permission_classes
from users.permissions import IsModeratorOrAdmin
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiParameter
from rest_framework import serializers

from places.models import Place

from .models import Review, ReviewLike, ReviewReport
from .serializers import (
    ReviewSerializer,
    ReviewCreateSerializer,
    ReviewUpdateSerializer,
    ReviewReportSerializer,
    ModerateReviewSerializer,
)
from notifications.models import Notification
from core.image_processing import process_uploaded_image_variants
from core.moderation import rejection_message, review_auto_reject_reason
from django.db import transaction, IntegrityError
from core.pagination import StandardPagination


def user_can_act(user):
    return (
        user.is_authenticated
        and user.is_active
        and not user.is_blocked
    )


def _attach_review_photos(review, files):
    if not files:
        return

    existing = review.photos.count()

    if existing + len(files) > 5:
        raise ValueError("Ба як отзыв максимум 5 сурат иҷозат аст.")

    for uploaded_file in files:
        variants = process_uploaded_image_variants(uploaded_file)
        ReviewPhoto.objects.create(
            review=review,
            image=variants["image"],
            thumbnail=variants["thumbnail"],
        )


def _delete_review_photo_files(photo):
    if photo.image:
        photo.image.delete(save=False)

    if photo.thumbnail:
        photo.thumbnail.delete(save=False)


def _rejection_notification(review, reason_text):
    language = getattr(review.user, "language", "ru")
    messages = {
        "ru": (
            "Отзыв отклонён",
            "Ваш отзыв отклонён автоматически. Причина: ",
        ),
        "tg": (
            "Отзыв рад шуд",
            "Отзыви шумо ба таври худкор рад шуд. Сабаб: ",
        ),
        "en": (
            "Review rejected",
            "Your review was rejected automatically. Reason: ",
        ),
    }
    title, message = messages.get(language, messages["ru"])

    Notification.objects.create(
        user=review.user,
        notification_type=Notification.Type.REVIEW_REJECTED,
        title=title,
        message=message + reason_text,
        review=review,
    )



@extend_schema(
    request=ReviewCreateSerializer,
    responses={
        200: ReviewSerializer(many=True),
        201: inline_serializer(
            name="ReviewCreateResponse",
            fields={
                "detail": serializers.CharField(),
                "review": ReviewSerializer(),
            },
        ),
    },
)
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def place_reviews(request, slug):
    """Гирифтан ва фиристодани отзывҳои ҷой."""

    place = get_object_or_404(
        Place,
        slug=slug,
        status=Place.Status.PUBLISHED,
    )

    if request.method == "GET":
        reviews = (
            Review.objects.filter(
                place=place,
                status=Review.Status.APPROVED,
            )
            .select_related("user", "place")
            .prefetch_related("likes", "photos")
            .order_by("-created_at")
        )

        paginator = StandardPagination()
        page = paginator.paginate_queryset(reviews, request)
        serializer = ReviewSerializer(
            page,
            many=True,
            context={"request": request},
        )
        return paginator.get_paginated_response(serializer.data)

    if not request.user.is_authenticated:
        return Response(
            {"detail": "Барои фиристодани отзыв ворид шавед."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user_can_act(request.user):
        return Response(
            {"detail": "Аккаунти шумо барои ин амал иҷозат надорад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if Review.objects.filter(
        user=request.user,
        place=place,
    ).exists():
        return Response(
            {"detail": "Шумо аллакай барои ин ҷой отзыв доред."},
            status=status.HTTP_400_BAD_REQUEST,
        )


    now = timezone.now()
    local_now = timezone.localtime(now)
    today_start = local_now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    tomorrow_start = today_start + timedelta(days=1)

    daily_count = Review.objects.filter(
        user=request.user,
        created_at__gte=today_start,
        created_at__lt=tomorrow_start,
    ).count()

    if daily_count >= 5:
        return Response(
            {"detail": "Дар як рӯз на бештар аз 5 отзыв фиристодан мумкин аст."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    serializer = ReviewCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    rejection_reason = review_auto_reject_reason(
        serializer.validated_data["text"]
    )
    review_status = (
        Review.Status.REJECTED
        if rejection_reason
        else Review.Status.PENDING
    )

    photo_files = serializer.validated_data.pop("photos", [])

    try:
        with transaction.atomic():
            review = serializer.save(
                user=request.user,
                place=place,
                status=review_status,
                moderation_note=rejection_reason or "",
            )
            _attach_review_photos(review, photo_files)
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except IntegrityError:
        return Response(
            {"detail": "Шумо аллакай барои ин ҷой отзыв доред."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if rejection_reason:
        language = getattr(request.user, "language", "ru")
        reason_text = rejection_message(rejection_reason, language)
        _rejection_notification(review, reason_text)

        return Response(
            {
                "detail": (
                    "Отзыв отклонён автоматически. "
                    f"Причина: {reason_text}"
                ),
                "review": ReviewSerializer(
                    review,
                    context={"request": request},
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )

    return Response(
        {
            "detail": "Отзыв қабул шуд ва интизори санҷиш аст.",
            "review": ReviewSerializer(
                review,
                context={"request": request},
            ).data,
        },
        status=status.HTTP_201_CREATED,
    )


@extend_schema(
    request=ReviewUpdateSerializer,
    responses={
        200: inline_serializer(
            name="ReviewUpdateResponse",
            fields={
                "detail": serializers.CharField(),
                "review": ReviewSerializer(),
            },
        ),
        204: None,
    },
)
@api_view(["PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def review_detail(request, review_id):
    """Таҳрир ё нест кардани отзыви худи корбар."""

    if not request.user.is_authenticated:
        return Response(
            {"detail": "Барои ин амал ворид шавед."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user_can_act(request.user):
        return Response(
            {"detail": "Аккаунти шумо барои ин амал иҷозат надорад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    review = get_object_or_404(
        Review,
        id=review_id,
        user=request.user,
    )

    if request.method == "DELETE":
        photos = list(review.photos.all())
        review.delete()
        for photo in photos:
            _delete_review_photo_files(photo)
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ReviewUpdateSerializer(
        review,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)

    photo_files = serializer.validated_data.pop("photos", [])
    remove_photo_ids = serializer.validated_data.pop(
        "remove_photo_ids",
        [],
    )
    photos_to_remove = list(
        review.photos.filter(id__in=remove_photo_ids)
    )

    remaining_photos = review.photos.count() - len(photos_to_remove)
    if remaining_photos + len(photo_files) > 5:
        return Response(
            {"detail": "Ба як отзыв максимум 5 сурат иҷозат аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    new_text = serializer.validated_data.get("text", review.text)
    rejection_reason = review_auto_reject_reason(new_text)
    review_status = (
        Review.Status.REJECTED
        if rejection_reason
        else Review.Status.PENDING
    )

    try:
        with transaction.atomic():
            if photos_to_remove:
                review.photos.filter(
                    id__in=[photo.id for photo in photos_to_remove]
                ).delete()

            serializer.save(
                status=review_status,
                moderator=None,
                moderation_note=rejection_reason or "",
            )
            _attach_review_photos(review, photo_files)
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    for photo in photos_to_remove:
        _delete_review_photo_files(photo)

    if rejection_reason:
        language = getattr(request.user, "language", "ru")
        reason_text = rejection_message(rejection_reason, language)
        _rejection_notification(review, reason_text)

    return Response(
        {
            "detail": "Отзыв тағйир ёфт ва ба санҷиш фиристода шуд.",
            "review": ReviewSerializer(
                review,
                context={"request": request},
            ).data,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    request=None,
    responses={
        200: inline_serializer(
            name="ReviewLikeResponse",
            fields={
                "detail": serializers.CharField(),
                "likes_count": serializers.IntegerField(),
                "is_liked": serializers.BooleanField(),
            },
        ),
        201: inline_serializer(
            name="ReviewLikeCreatedResponse",
            fields={
                "detail": serializers.CharField(),
                "likes_count": serializers.IntegerField(),
                "is_liked": serializers.BooleanField(),
            },
        ),
    },
)
@api_view(["POST", "DELETE"])
def review_like(request, review_id):
    """Гузоштан ё гирифтани лайк."""

    if not request.user.is_authenticated:
        return Response(
            {"detail": "Барои лайк мондан ворид шавед."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user_can_act(request.user):
        return Response(
            {"detail": "Аккаунти шумо барои ин амал иҷозат надорад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    review = get_object_or_404(
        Review,
        id=review_id,
        status=Review.Status.APPROVED,
    )

    if request.method == "POST":
        _, created = ReviewLike.objects.get_or_create(
            user=request.user,
            review=review,
        )

        return Response(
            {
                "detail": (
                    "Лайк гузошта шуд."
                    if created
                    else "Шумо аллакай лайк гузоштаед."
                ),
                "likes_count": review.likes.count(),
                "is_liked": True,
            },
            status=(
                status.HTTP_201_CREATED
                if created
                else status.HTTP_200_OK
            ),
        )

    ReviewLike.objects.filter(
        user=request.user,
        review=review,
    ).delete()

    return Response(
        {
            "detail": "Лайк гирифта шуд.",
            "likes_count": review.likes.count(),
            "is_liked": False,
        },
        status=status.HTTP_200_OK,
    )


@extend_schema(
    request=ReviewReportSerializer,
    responses={
        201: inline_serializer(
            name="ReviewReportResponse",
            fields={
                "detail": serializers.CharField(),
                "report_id": serializers.IntegerField(),
            },
        ),
    },
)
@api_view(["POST"])
def review_report(request, review_id):
    """Шикоят аз отзыви нашршуда."""

    if not request.user.is_authenticated:
        return Response(
            {"detail": "Барои шикоят кардан ворид шавед."},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if not user_can_act(request.user):
        return Response(
            {"detail": "Аккаунти шумо барои ин амал иҷозат надорад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    review = get_object_or_404(
        Review,
        id=review_id,
        status=Review.Status.APPROVED,
    )

    if review.user_id == request.user.id:
        return Response(
            {"detail": "Аз отзыви худ шикоят карда намешавад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = ReviewReportSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    report, created = ReviewReport.objects.get_or_create(
        user=request.user,
        review=review,
        defaults={
            "reason": serializer.validated_data["reason"],
        },
    )

    if not created:
        return Response(
            {"detail": "Шумо аллакай аз ин отзыв шикоят кардаед."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response(
        {
            "detail": "Шикояти шумо қабул шуд.",
            "report_id": report.id,
        },
        status=status.HTTP_201_CREATED,
    )




@extend_schema(
    tags=["Admin - Reviews"],
    summary="Рӯйхати отзывҳо барои модератсия",
    description=(
        "Рӯйхати отзывҳоро аз рӯи статус филтр мекунад. "
        "Статуси пешфарз pending аст. "
        "Барои дидани отзывҳои нашршуда published ё approved истифода баред."
    ),
    parameters=[
        OpenApiParameter(
            name="status",
            type=str,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Статуси отзыв",
            enum=["pending", "approved", "published", "rejected"],
        ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Рақами саҳифа",
        ),
        OpenApiParameter(
            name="limit",
            type=int,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Шумораи отзывҳо дар як саҳифа (1–100)",
        ),
    ],
    responses={200: dict},
)
@api_view(["GET"])
@permission_classes([IsModeratorOrAdmin])
def moderation_queue(request):
    """Рӯйхати отзывҳо барои модератор."""

    status_value = request.query_params.get("status", "pending")

    if status_value == "published":
        status_value = Review.Status.APPROVED
    elif status_value not in Review.Status.values:
        status_value = "pending"

    reviews = (
        Review.objects.filter(status=status_value)
        .select_related("user", "place", "moderator")
        .order_by("created_at")
    )

    try:
        page = max(int(request.query_params.get("page", 1)), 1)
    except (TypeError, ValueError):
        page = 1

    try:
        limit = int(request.query_params.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20

    limit = min(max(limit, 1), 100)
    total = reviews.count()
    offset = (page - 1) * limit
    page_reviews = reviews[offset:offset + limit]

    serializer = ReviewSerializer(
        page_reviews,
        many=True,
        context={"request": request},
    )

    return Response({
        "count": total,
        "total": total,
        "page": page,
        "limit": limit,
        "results": serializer.data,
        "items": serializer.data,
    })



def _moderate_review_impl(request, review_id, forced_action=None):
    """Нашр ё рад кардани отзыв бо сабаб."""

    review = get_object_or_404(
        Review,
        id=review_id,
        status=Review.Status.PENDING,
    )

    action = forced_action or request.data.get("action")
    reason = str(request.data.get("reason", "")).strip()

    if action not in ("approve", "reject"):
        return Response(
            {"detail": "action бояд approve ё reject бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if action == "reject" and not reason:
        return Response(
            {"detail": "Ҳангоми рад кардан сабабро нависед."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    review.status = (
        Review.Status.APPROVED
        if action == "approve"
        else Review.Status.REJECTED
    )
    review.moderator = request.user
    review.moderation_note = "" if action == "approve" else reason
    review.save(
        update_fields=[
            "status",
            "moderator",
            "moderation_note",
            "updated_at",
        ]
    )

    language = getattr(review.user, "language", "ru")

    messages = {
        "ru": {
            "approved_title": "Отзыв опубликован",
            "approved_message": "Ваш отзыв опубликован.",
            "rejected_title": "Отзыв отклонён",
            "rejected_message": "Ваш отзыв отклонён. Причина: ",
        },
        "tg": {
            "approved_title": "Отзыв нашр шуд",
            "approved_message": "Отзыви шумо нашр шуд.",
            "rejected_title": "Отзыв рад шуд",
            "rejected_message": "Отзыви шумо рад шуд. Сабаб: ",
        },
        "en": {
            "approved_title": "Review published",
            "approved_message": "Your review has been published.",
            "rejected_title": "Review rejected",
            "rejected_message": "Your review was rejected. Reason: ",
        },
    }

    text = messages.get(language, messages["ru"])

    if action == "approve":
        title = text["approved_title"]
        message = text["approved_message"]
        notification_type = Notification.Type.REVIEW_APPROVED
    else:
        title = text["rejected_title"]
        message = text["rejected_message"] + reason
        notification_type = Notification.Type.REVIEW_REJECTED

    Notification.objects.create(
        user=review.user,
        notification_type=notification_type,
        title=title,
        message=message,
        review=review,
    )


    return Response({
        "detail": (
            "Отзыв нашр шуд."
            if action == "approve"
            else "Отзыв рад карда шуд."
        ),
        "review_id": review.id,
        "status": ReviewSerializer(
            review,
            context={"request": request},
        ).data["status"],
        "reason": review.moderation_note,
    })



@extend_schema(
    tags=["Admin - Reviews"],
    summary="Тасдиқи отзыв",
    request=None,
    responses={200: dict},
)
@api_view(["POST"])
@permission_classes([IsModeratorOrAdmin])
def admin_review_approve(request, review_id):
    return _moderate_review_impl(request, review_id, forced_action="approve")


@extend_schema(
    tags=["Admin - Reviews"],
    summary="Рад кардани отзыв",
    request=ModerateReviewSerializer,
    responses={200: dict, 400: dict, 404: dict},
)
@api_view(["POST"])
@permission_classes([IsModeratorOrAdmin])
def admin_review_reject(request, review_id):
    return _moderate_review_impl(request, review_id, forced_action="reject")


@extend_schema(
    tags=["Reviews"],
    summary="Нест кардани акси отзыв",
    responses={204: None, 403: dict, 404: dict},
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def review_photo_delete(request, review_id, photo_id):
    if not user_can_act(request.user):
        return Response(
            {"detail": "Аккаунти шумо барои ин амал иҷозат надорад."},
            status=status.HTTP_403_FORBIDDEN,
        )

    review = get_object_or_404(
        Review,
        id=review_id,
        user=request.user,
    )
    photo = get_object_or_404(
        ReviewPhoto,
        id=photo_id,
        review=review,
    )

    _delete_review_photo_files(photo)
    photo.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["Reviews"],
    summary="Бор кардани акси отзыв",
    request=inline_serializer(
        name="ReviewPhotoUploadRequest",
        fields={
            "image": serializers.ImageField(),
        },
    ),
    responses={
        201: inline_serializer(
            name="ReviewPhotoUploadResponse",
            fields={
                "id": serializers.IntegerField(),
                "image": serializers.URLField(),
                "created_at": serializers.DateTimeField(),
            },
        ),
        400: inline_serializer(
            name="ReviewPhotoUploadError",
            fields={
                "detail": serializers.CharField(),
            },
        ),
        403: inline_serializer(
            name="ReviewPhotoUploadForbidden",
            fields={
                "detail": serializers.CharField(),
            },
        ),
        404: inline_serializer(
            name="ReviewPhotoUploadNotFound",
            fields={
                "detail": serializers.CharField(),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def review_photo_upload(request, review_id):
    user = request.user

    if not user.is_active or getattr(user, "is_blocked", False):
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        review = Review.objects.get(
            id=review_id,
            user=user,
        )
    except Review.DoesNotExist:
        return Response(
            {"detail": "Отзыв ёфт нашуд."},
            status=status.HTTP_404_NOT_FOUND,
        )


    uploaded_file = request.FILES.get("image")

    if not uploaded_file:
        return Response(
            {"detail": "Файли image ҳатмист."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if ReviewPhoto.objects.filter(review=review).count() >= 5:
        return Response(
            {"detail": "Ба як отзыв максимум 5 сурат иҷозат аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        image_variants = process_uploaded_image_variants(
        uploaded_file
    )
    except ValueError as exc:
        return Response(
        {"detail": str(exc)},
        status=status.HTTP_400_BAD_REQUEST,
    )

    with transaction.atomic():
        # Сабти отзывро муваққатан қулф мекунем.
        review = Review.objects.select_for_update().get(
            id=review_id,
            user=user,
        )

        # Бори дигар шумораи аксҳоро месанҷем.
        photo_count = ReviewPhoto.objects.filter(
            review=review
        ).count()

        if photo_count >= 5:
            return Response(
                {"detail": "Ба як отзыв максимум 5 сурат иҷозат аст."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Агар лимит пур нашуда бошад, аксро захира мекунем.
        photo = ReviewPhoto.objects.create(
            review=review,
            image=image_variants["image"],
            thumbnail=image_variants["thumbnail"],
        )

    return Response(
    {
        "id": photo.id,
        "image": request.build_absolute_uri(
            photo.image.url
        ),
        "thumbnail": request.build_absolute_uri(
            photo.thumbnail.url
        ),
        "created_at": photo.created_at,
    },
    status=status.HTTP_201_CREATED,
)



def _serialize_moderation_reports(reports):
    return [
        {
            "id": report.id,
            "review_id": report.review_id,
            "place_name": report.review.place.name,
            "reporter_id": report.user_id,
            "reason": report.reason,
            "status": report.status,
            "created_at": report.created_at,
        }
        for report in reports
    ]


@extend_schema(
    tags=["Admin - Reports"],
    summary="Рӯйхати шикоятҳо",
    parameters=[
        OpenApiParameter(
            name="status",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["pending", "resolved"],
            required=False,
        ),
        OpenApiParameter("page", int, required=False),
        OpenApiParameter("limit", int, required=False),
        OpenApiParameter("page_size", int, required=False),
    ],
    responses={
        200: inline_serializer(
            name="ModerationReportsResponse",
            many=True,
            fields={
                "id": serializers.IntegerField(),
                "review_id": serializers.IntegerField(),
                "place_name": serializers.JSONField(),
                "reporter_id": serializers.IntegerField(),
                "reason": serializers.CharField(),
                "status": serializers.CharField(),
                "created_at": serializers.DateTimeField(),
            },
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsModeratorOrAdmin])
def moderation_reports(request):
    reports = (
        ReviewReport.objects
        .select_related("user", "review", "review__place")
        .order_by("-created_at")
    )

    report_status = request.query_params.get("status")

    if report_status in {"pending", "resolved"}:
        reports = reports.filter(status=report_status)

    pagination_requested = any(
        key in request.query_params
        for key in ("page", "limit", "page_size")
    )

    if pagination_requested:
        paginator = StandardPagination()
        page = paginator.paginate_queryset(reports, request)
        results = _serialize_moderation_reports(page)
        return paginator.get_paginated_response(results)

    results = _serialize_moderation_reports(reports[:200])
    return Response(results)



@extend_schema(
    tags=["Admin - Reports"],
    summary="Ҳал кардани шикоят",
    request=None,
    responses={
        200: inline_serializer(
            name="ResolveReportResponse",
            fields={
                "detail": serializers.CharField(),
                "report_id": serializers.IntegerField(),
                "status": serializers.CharField(),
            },
        ),
        404: inline_serializer(
            name="ResolveReportNotFound",
            fields={
                "detail": serializers.CharField(),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsModeratorOrAdmin])
def resolve_report(request, report_id):
    try:
        report = ReviewReport.objects.select_related(
            "review", "user"
        ).get(id=report_id)
    except ReviewReport.DoesNotExist:
        return Response(
            {"detail": "Шикоят ёфт нашуд."},
            status=status.HTTP_404_NOT_FOUND,
        )

    report.status = "resolved"
    report.save(update_fields=["status"])

    return Response({
        "detail": "Шикоят ҳал карда шуд.",
        "report_id": report.id,
        "status": report.status,
    })
