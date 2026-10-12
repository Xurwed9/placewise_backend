
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from places.models import Place
from .models import Review
from .serializers import ReviewSerializer, ReviewCreateSerializer



@extend_schema(
    request=ReviewCreateSerializer,
    responses={
        201: ReviewSerializer,
        400: dict,
        401: dict,
        403: dict,
        404: dict,
    },
)
@api_view(["GET", "POST"])
def place_reviews(request, slug):
    place = get_object_or_404(
        Place,
        slug=slug,
        status="published",
    )

    if request.method == "GET":
        reviews = (
            Review.objects
            .filter(place=place, status=Review.Status.APPROVED)
            .select_related("user", "place")
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

    if not request.user.is_active or request.user.is_blocked:
        return Response(
            {"detail": "Аккаунти шумо барои ин амал иҷозат надорад."},
            status=status.HTTP_403_FORBIDDEN,
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
