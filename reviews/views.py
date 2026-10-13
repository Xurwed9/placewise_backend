
from django.shortcuts import get_object_or_404
from io import BytesIO
from PIL import Image
from rest_framework.decorators import (
    api_view,
    permission_classes,
    parser_classes,
)
from rest_framework.parsers import MultiPartParser, FormParser
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
from drf_spectacular.utils import extend_schema


from places.models import Place

from .models import Review, ReviewLike, ReviewReport
from .serializers import (
    ReviewSerializer,
    ReviewCreateSerializer,
    ReviewUpdateSerializer,
    ReviewReportSerializer,
)
from notifications.models import Notification


def user_can_act(user):
    return (
        user.is_authenticated
        and user.is_active
        and not user.is_blocked
    )


@api_view(["GET", "POST"])
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
            .prefetch_related("likes")
            .order_by("-created_at")
        )

        serializer = ReviewSerializer(
            reviews,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

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

    review = serializer.save(
        user=request.user,
        place=place,
        status=Review.Status.PENDING,
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


@api_view(["PATCH", "DELETE"])
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
        review.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = ReviewUpdateSerializer(
        review,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(
        status=Review.Status.PENDING,
        moderator=None,
        moderation_note="",
    )

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
    responses={200: ReviewSerializer(many=True)}
)
@api_view(["GET"])
@permission_classes([IsModeratorOrAdmin])
def moderation_queue(request):
    """Рӯйхати отзывҳои интизори санҷиш."""

    reviews = (
        Review.objects.filter(status=Review.Status.PENDING)
        .select_related("user", "place", "moderator")
        .order_by("created_at")
    )

    serializer = ReviewSerializer(
        reviews,
        many=True,
        context={"request": request},
    )

    return Response({
        "count": reviews.count(),
        "results": serializer.data,
    })


@extend_schema(
    request={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["approve", "reject"],
            },
            "reason": {"type": "string"},
        },
        "required": ["action"],
    },
    responses={200: dict, 400: dict, 404: dict},
)
@api_view(["POST"])
@permission_classes([IsModeratorOrAdmin])
def moderate_review(request, review_id):
    """Нашр ё рад кардани отзыв бо сабаб."""

    review = get_object_or_404(
        Review,
        id=review_id,
        status=Review.Status.PENDING,
    )

    action = request.data.get("action")
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
        "status": review.status,
        "reason": review.moderation_note,
    })




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

    if uploaded_file.size > 10 * 1024 * 1024:
        return Response(
            {"detail": "Андозаи сурат набояд аз 10 MB зиёд бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image_format = image.format

        if image_format not in {"JPEG", "PNG", "WEBP"}:
            return Response(
                {"detail": "Танҳо JPEG, PNG ё WEBP иҷозат аст."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        image.verify()
        uploaded_file.seek(0)

    except Exception:
        return Response(
            {"detail": "Файли сурат нодуруст аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if ReviewPhoto.objects.filter(review=review).count() >= 5:
        return Response(
            {"detail": "Ба як отзыв максимум 5 сурат иҷозат аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    photo = ReviewPhoto.objects.create(
        review=review,
        image=uploaded_file,
    )

    return Response(
        {
            "id": photo.id,
            "image": request.build_absolute_uri(photo.image.url),
            "created_at": photo.created_at,
        },
        status=status.HTTP_201_CREATED,
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

    results = []

    for report in reports[:200]:
        results.append({
            "id": report.id,
            "review_id": report.review_id,
            "place_name": report.review.place.name,
            "reporter_id": report.user_id,
            "reason": report.reason,
            "status": report.status,
            "created_at": report.created_at,
        })

    return Response(results)


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


