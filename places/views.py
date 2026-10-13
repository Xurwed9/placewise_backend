from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from django.core.files.storage import default_storage
from rest_framework.decorators import parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, TextField, Count
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.contrib.gis.geos import Polygon
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsPlacewiseAdmin
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers
from django.utils import timezone
from django.db import transaction
from rest_framework.response import Response
from rest_framework import status
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db.models import ExpressionWrapper, FloatField
from datetime import datetime, time
from zoneinfo import ZoneInfo

from .models import Category, Place,Favorite,Claim
from .serializers import (
    CategorySerializer,
    PlaceListSerializer,
    PlaceDetailSerializer,
    FavoriteSerializer,
    PlacePaginationSerializer,
    OwnerPlaceUpdateSerializer, ClaimCreateSerializer,
    ClaimSerializer, AdminPlaceUpdateSerializer,
)
from reviews.models import Review
from reviews.serializers import ReviewSerializer
from notifications.models import Notification


class PlacePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100




@extend_schema(
    parameters=[
        OpenApiParameter(
            name="lang",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоби API: tg — тоҷикӣ, ru — русӣ, en — англисӣ",
        ),
    ],
    responses=CategorySerializer(many=True),
)
@api_view(["GET"])
def category_list(request):
    categories = (
        Category.objects
        .filter(is_active=True)
        .annotate(
            place_count=Count(
                "places",
                filter=Q(
                    places__status=Place.Status.PUBLISHED
                ),
            )
        )
    )

    serializer = CategorySerializer(
        categories,
        many=True,
        context={"request": request},
    )

    return Response(serializer.data)



def get_open_now(opening_hours):
    """
    Формати соатҳо:
    {
        "mon": {"open": "09:00", "close": "18:00"},
        "tue": {"open": "09:00", "close": "18:00"},
        ...
    }

    Агар соатҳо муайян нашуда бошанд, None бармегардонад.
    """
    if not isinstance(opening_hours, dict) or not opening_hours:
        return None

    now = datetime.now(ZoneInfo("Asia/Dushanbe"))

    day_keys = [
        "mon", "tue", "wed", "thu", "fri", "sat", "sun"
    ]
    today = day_keys[now.weekday()]
    hours = opening_hours.get(today)

    if not isinstance(hours, dict):
        return None

    if hours.get("closed") is True:
        return False

    opening = hours.get("open")
    closing = hours.get("close")

    if not opening or not closing:
        return None

    try:
        open_time = time.fromisoformat(opening)
        close_time = time.fromisoformat(closing)
    except (ValueError, TypeError):
        return None

    current_time = now.time().replace(tzinfo=None)

    if open_time <= close_time:
        return open_time <= current_time < close_time

    return current_time >= open_time or current_time < close_time



@extend_schema(
    operation_id="place_list",
    responses=PlacePaginationSerializer,
    parameters=[
        OpenApiParameter(
        name="open_now",
        type=bool,
        location=OpenApiParameter.QUERY,
        description="Филтр: ҷой ҳоло кушода аст ё не",
        ),
        OpenApiParameter(
            name="lat",
            type=float,
            location=OpenApiParameter.QUERY,
            description="Арзи ҷуғрофӣ, масалан 38.5598",
        ),
        OpenApiParameter(
            name="lon",
            type=float,
            location=OpenApiParameter.QUERY,
            description="Тӯли ҷуғрофӣ, масалан 68.7870",
        ),
        OpenApiParameter(
            name="radius",
            type=float,
            location=OpenApiParameter.QUERY,
            description="Радиуси ҷустуҷӯ бо километр; аз 0.1 то 100",
        ),
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб: tg — тоҷикӣ, ru — русӣ, en — англисӣ",
            ),
        OpenApiParameter(
            name="page",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Рақами саҳифа, аз 1 сар мешавад",
        ),
        OpenApiParameter(
            name="page_size",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Шумораи ҷойҳо дар як саҳифа, ҳадди аксар 100",
        ),
        OpenApiParameter(
            name="search",
            type=str,
            location=OpenApiParameter.QUERY,
            description="Ҷустуҷӯ аз рӯйи ном, суроға, slug ё ноҳия",
        ),
        OpenApiParameter(
            name="category",
            type=str,
            location=OpenApiParameter.QUERY,
            description="Slug-и категория, масалан cafe",
        ),
        OpenApiParameter(
            name="district",
            type=str,
            location=OpenApiParameter.QUERY,
            description="Номи ноҳия",
        ),
        OpenApiParameter(
            name="min_rating",
            type=float,
            location=OpenApiParameter.QUERY,
            description="Рейтинги минималӣ аз 0 то 5",
        ),
        OpenApiParameter(
            name="price_level",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Сатҳи нарх аз 1 то 4",
        ),
        OpenApiParameter(
            name="ordering",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=[
                "rating",
                "-rating",
                "reviews_count",
                "-reviews_count",
                "created_at",
                "-created_at",
                "slug",
                "-slug",
                "distance",
            ],
            description="Тартиби навъбандӣ",
        ),
    ],
)
@api_view(["GET"])
def place_list(request):
    places = (
        Place.objects
        .filter(status=Place.Status.PUBLISHED)
        .select_related("category", "brand")
    )

    search = request.query_params.get("search", "").strip()

    if search:
        places = places.annotate(
            name_text=Cast("name", output_field=TextField()),
            address_text=Cast("address", output_field=TextField()),
        ).filter(
            Q(name_text__icontains=search)
            | Q(address_text__icontains=search)
            | Q(slug__icontains=search)
            | Q(district__icontains=search)
        )

    category = request.query_params.get("category", "").strip()

    if category:
        places = places.filter(category__slug=category)

    district = request.query_params.get("district", "").strip()

    if district:
        places = places.filter(district__icontains=district)

    min_rating = request.query_params.get("min_rating")

    if min_rating not in (None, ""):
        try:
            rating_value = float(min_rating)

            if not 0 <= rating_value <= 5:
                raise ValueError

        except (ValueError, TypeError):
            return Response(
                {"error": "min_rating бояд аз 0 то 5 бошад"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        places = places.filter(rating__gte=rating_value)

    price_level = request.query_params.get("price_level")

    if price_level not in (None, ""):
        try:
            price_value = int(price_level)

            if price_value not in {1, 2, 3, 4}:
                raise ValueError

        except (ValueError, TypeError):
            return Response(
                {
                    "error": (
                        "price_level бояд адади бутун "
                        "аз 1 то 4 бошад"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        places = places.filter(price_level=price_value)

    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    radius = request.query_params.get("radius", "5")
    open_now = request.query_params.get("open_now")

    location_point = None

    if (lat is None) != (lon is None):
        return Response(
            {"error": "lat ва lon бояд якҷоя дода шаванд"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if lat is not None:
        try:
            lat_value = float(lat)
            lon_value = float(lon)
            radius_value = float(radius)

            if not -90 <= lat_value <= 90:
                raise ValueError

            if not -180 <= lon_value <= 180:
                raise ValueError

            if not 0.1 <= radius_value <= 100:
                raise ValueError

        except (ValueError, TypeError):
            return Response(
                {
                    "error": (
                        "lat, lon ё radius нодуруст аст. "
                        "radius бояд аз 0.1 то 100 км бошад."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        location_point = Point(
            lon_value,
            lat_value,
            srid=4326,
        )

        places = places.filter(
            location__isnull=False,
            location__distance_lte=(
                location_point,
                D(km=radius_value),
            ),
        )

    if open_now not in (None, ""):
        if open_now.lower() not in {"true", "false"}:
            return Response(
                {"error": "open_now бояд true ё false бошад"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now().astimezone(
            ZoneInfo("Asia/Dushanbe")
        )

        day_keys = [
            "mon", "tue", "wed", "thu",
            "fri", "sat", "sun",
        ]
        today = day_keys[now.weekday()]
        current_time = now.strftime("%H:%M")

        matching_ids = []

        for place in places.only("id", "opening_hours").iterator():
            hours_data = place.opening_hours

            if not isinstance(hours_data, dict):
                continue

            today_hours = hours_data.get(today)

            if not isinstance(today_hours, dict):
                continue

            if today_hours.get("closed") is True:
                is_open = False
            else:
                opening = today_hours.get("open")
                closing = today_hours.get("close")

                if not opening or not closing:
                    continue

                try:
                    from datetime import time

                    start = time.fromisoformat(opening)
                    end = time.fromisoformat(closing)
                    current = time.fromisoformat(current_time)

                    if start <= end:
                        is_open = start <= current < end
                    else:
                        is_open = current >= start or current < end

                except (ValueError, TypeError):
                    continue

            if is_open == (open_now.lower() == "true"):
                matching_ids.append(place.id)

        places = places.filter(id__in=matching_ids)

    ordering = request.query_params.get("ordering", "-rating")

    allowed_ordering = {
        "rating",
        "-rating",
        "reviews_count",
        "-reviews_count",
        "created_at",
        "-created_at",
        "slug",
        "-slug",
        "distance",
    }

    if ordering not in allowed_ordering:
        return Response(
            {
                "error": "ordering нодуруст аст",
                "allowed": sorted(allowed_ordering),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if ordering == "distance":
        if location_point is None:
            return Response(
                {
                    "error": (
                        "Барои ordering=distance "
                        "параметрҳои lat ва lon лозиманд"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        places = places.annotate(
            distance=Distance("location", location_point)
        ).order_by("distance", "id")
    else:
        places = places.order_by(ordering, "id")

    places = places.order_by(ordering, "id")

    paginator = PlacePagination()
    page = paginator.paginate_queryset(places, request)

    serializer = PlaceListSerializer(
        page,
        many=True,
        context={"request": request},
    )

    return paginator.get_paginated_response(serializer.data)




@extend_schema(
    operation_id="place_detail",
    parameters=[
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб: tg — тоҷикӣ, ru — русӣ, en — англисӣ",
        ),
    ],
    responses=PlaceDetailSerializer,
)
@api_view(["GET"])
def place_detail(request, slug):
    place = get_object_or_404(
        Place.objects
        .filter(status=Place.Status.PUBLISHED)
        .select_related("category", "brand")
        .prefetch_related("photos"),
        slug=slug,
    )

    serializer = PlaceDetailSerializer(
        place,
        context={"request": request},
    )

    return Response(serializer.data)





@extend_schema(
    operation_id="place_map",
    parameters=[
        OpenApiParameter(
            name="bbox",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=True,
            description=(
                "west,south,east,north. "
                "Мисол: 68.70,38.45,68.85,38.65"
            ),
        ),
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб: tg — тоҷикӣ, ru — русӣ, en — англисӣ",
        ),
    ],
    responses={
        200: inline_serializer(
            name="PlaceMapResponse",
            fields={
                "count": serializers.IntegerField(),
                "results": PlaceListSerializer(many=True),
            },
        ),
        400: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET"])
def place_map(request):
    """
    Гирифтани ҷойҳо дар ҳудуди харита.
    bbox = west,south,east,north
    """
    bbox = request.query_params.get("bbox")

    if not bbox:
        return Response(
            {"error": "bbox лозим аст: west,south,east,north"},
            status=400,
        )

    try:
        west, south, east, north = map(float, bbox.split(","))

        if not (
            -180 <= west <= 180
            and -180 <= east <= 180
            and -90 <= south <= 90
            and -90 <= north <= 90
            and west < east
            and south < north
        ):
            raise ValueError

    except (ValueError, TypeError):
        return Response(
            {"error": "bbox нодуруст аст"},
            status=400,
        )

    area = Polygon.from_bbox((west, south, east, north))
    area.srid = 4326

    places = (
        Place.objects
        .filter(
            status=Place.Status.PUBLISHED,
            location__isnull=False,
            location__intersects=area,
        )
        .select_related("category", "brand")
    )

    serializer = PlaceListSerializer(
        places[:500],
        many=True,
        context={"request": request},
    )

    return Response({
        "count": places.count(),
        "results": serializer.data,
    })





@extend_schema(
    operation_id="similar_places",
    parameters=[
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб: tg — тоҷикӣ, ru — русӣ, en — англисӣ",
        ),
    ],
    responses={
        200: inline_serializer(
            name="SimilarPlacesResponse",
            fields={
                "place": serializers.CharField(),
                "count": serializers.IntegerField(),
                "results": PlaceListSerializer(many=True),
            },
        ),
        404: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET"])
def similar_places(request, slug):
    place = get_object_or_404(
        Place.objects.select_related("category"),
        slug=slug,
        status=Place.Status.PUBLISHED,
    )

    similar = (
        Place.objects
        .filter(
            category=place.category,
            status=Place.Status.PUBLISHED,
        )
        .exclude(id=place.id)
        .select_related("category", "brand")
        .order_by("-rating", "-reviews_count")[:6]
    )

    serializer = PlaceListSerializer(
        similar,
        many=True,
        context={"request": request},
    )

    return Response({
        "place": place.slug,
        "count": len(serializer.data),
        "results": serializer.data,
    })



@extend_schema(
    request=FavoriteSerializer,
    responses={201: FavoriteSerializer, 200: FavoriteSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def favorite_list(request):
    if request.method == "GET":
        favorites = (
            Favorite.objects
            .filter(user=request.user)
            .select_related("place")
        )

        serializer = FavoriteSerializer(
            favorites,
            many=True,
            context={
                "request": request,
                "language": request.query_params.get("lang", "ru"),
            },
        )
        return Response(serializer.data)

    place_id = request.data.get("place")

    if not place_id:
        return Response(
            {"error": "place лозим аст"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    place = get_object_or_404(
        Place,
        id=place_id,
        status=Place.Status.PUBLISHED,
    )

    favorite, created = Favorite.objects.get_or_create(
        user=request.user,
        place=place,
    )

    serializer = FavoriteSerializer(
        favorite,
        context={
            "request": request,
            "language": request.query_params.get("lang", "ru"),
        },
    )

    return Response(
        serializer.data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )



@extend_schema(
    operation_id="favorite_delete",
    responses={
        204: None,
        404: OpenApiTypes.OBJECT,
    },
)
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def favorite_delete(request, place_id):
    favorite = get_object_or_404(
        Favorite,
        user=request.user,
        place_id=place_id,
    )

    favorite.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)



@extend_schema(
    operation_id="home",
    summary="Маълумоти асосии саҳифаи хонагӣ",
    parameters=[
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб",
        ),
    ],
    responses={
        200: inline_serializer(
            name="HomeResponse",
            fields={
                "popular_places": PlaceListSerializer(many=True),
                "categories": CategorySerializer(many=True),
                "recent_reviews": ReviewSerializer(many=True),
                "places_count": serializers.IntegerField(),
                "categories_count": serializers.IntegerField(),
            },
        ),
    },
)
@extend_schema(
    operation_id="home",
    parameters=[
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб",
        ),
    ],
)
@api_view(["GET"])
def home(request):
    popular_places = (
        Place.objects
        .filter(status=Place.Status.PUBLISHED)
        .select_related("category", "brand")
        .order_by("-rating", "-reviews_count")[:6]
    )

    categories = (
        Category.objects
        .filter(is_active=True)
        .annotate(
            place_count=Count(
                "places",
                filter=Q(
                    places__status=Place.Status.PUBLISHED
                ),
            )
        )
        .order_by("sort_order", "id")
    )

    recent_reviews = (
        Review.objects
        .filter(
            status=Review.Status.APPROVED,
            place__status=Place.Status.PUBLISHED,
            user__is_active=True,
            user__is_blocked=False,
        )
        .select_related("user", "place")
        .order_by("-created_at")[:6]
    )

    places_data = PlaceListSerializer(
        popular_places,
        many=True,
        context={"request": request},
    ).data

    categories_data = CategorySerializer(
        categories,
        many=True,
        context={"request": request},
    ).data

    reviews_data = ReviewSerializer(
        recent_reviews,
        many=True,
    ).data

    return Response({
        "popular_places": places_data,
        "categories": categories_data,
        "recent_reviews": reviews_data,
        "places_count": Place.objects.filter(
            status=Place.Status.PUBLISHED
        ).count(),
        "categories_count": Category.objects.filter(
            is_active=True
        ).count(),
    })



@extend_schema(
    operation_id="search_suggest",
    parameters=[
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            required=True,
            description="Матни ҷустуҷӯ",
        ),
        OpenApiParameter(
            name="lang",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["tg", "ru", "en"],
            description="Забони ҷавоб",
        ),
    ],
    responses={
        200: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET"])
def search_suggest(request):
    query = request.query_params.get("q", "").strip()

    if not query:
        return Response({
            "places": [],
            "categories": [],
        })

    places = (
        Place.objects
        .filter(
            status=Place.Status.PUBLISHED,
            category__is_active=True,
        )
        .annotate(
            name_text=Cast("name", output_field=TextField()),
            address_text=Cast("address", output_field=TextField()),
        )
        .filter(
            Q(name_text__icontains=query)
            | Q(address_text__icontains=query)
            | Q(slug__icontains=query)
            | Q(district__icontains=query)
        )
        .select_related("category", "brand")
        .order_by("-rating", "-reviews_count")[:8]
    )

    categories = (
        Category.objects
        .filter(is_active=True)
        .annotate(
            name_text=Cast("name", output_field=TextField())
        )
        .filter(
            Q(name_text__icontains=query)
            | Q(slug__icontains=query)
            | Q(key__icontains=query)
        )
        .order_by("sort_order", "id")[:8]
    )

    return Response({
        "places": PlaceListSerializer(
            places,
            many=True,
            context={"request": request},
        ).data,
        "categories": CategorySerializer(
            categories,
            many=True,
            context={"request": request},
        ).data,
    })



@extend_schema(
    summary="Рӯйхати ҷойҳои соҳиби аккаунт",
    responses={
        200: inline_serializer(
            name="OwnerPlacesResponse",
            fields={
                "count": serializers.IntegerField(),
                "results": PlaceDetailSerializer(many=True),
            },
        ),
        403: inline_serializer(
            name="OwnerPlacesForbiddenResponse",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_places(request):
    """Рӯйхати ҷойҳое, ки ба соҳиб тааллуқ доранд."""

    if not request.user.is_active or request.user.is_blocked:
        return Response(
            {"detail": "Аккаунти шумо фаъол нест."},
            status=status.HTTP_403_FORBIDDEN,
        )

    places = (
        Place.objects.filter(owner=request.user)
        .select_related("category", "brand")
        .prefetch_related("photos")
        .order_by("-updated_at")
    )

    serializer = PlaceDetailSerializer(
        places,
        many=True,
        context={"request": request},
    )

    return Response({
        "count": places.count(),
        "results": serializer.data,
    })



@extend_schema(
    summary="Таҳрири ҷойи худ",
    request=OwnerPlaceUpdateSerializer,
    responses={
        200: inline_serializer(
            name="OwnerPlaceUpdateResponse",
            fields={
                "detail": serializers.CharField(),
                "place": PlaceDetailSerializer(),
            },
        ),
        403: inline_serializer(
            name="OwnerPlaceUpdateForbiddenResponse",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def owner_place_update(request, place_id):
    """Таҳрири ҷойи худи соҳиб."""

    if not request.user.is_active or request.user.is_blocked:
        return Response(
            {"detail": "Аккаунти шумо фаъол нест."},
            status=status.HTTP_403_FORBIDDEN,
        )

    place = get_object_or_404(
        Place,
        id=place_id,
        owner=request.user,
    )

    serializer = OwnerPlaceUpdateSerializer(
        place,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response({
        "detail": "Маълумоти ҷой нав карда шуд.",
        "place": PlaceDetailSerializer(
            place,
            context={"request": request},
        ).data,
    })



@extend_schema(
    summary="Ҷавоб додан ба отзыв",
    request=inline_serializer(
        name="OwnerReviewReplyRequest",
        fields={"reply": serializers.CharField()},
    ),
    responses={
        200: inline_serializer(
            name="OwnerReviewReplyResponse",
            fields={
                "detail": serializers.CharField(),
                "review_id": serializers.IntegerField(),
                "owner_reply": serializers.CharField(),
                "owner_reply_at": serializers.DateTimeField(
                    allow_null=True,
                ),
            },
        ),
        400: inline_serializer(
            name="OwnerReviewReplyBadRequest",
            fields={"detail": serializers.CharField()},
        ),
        403: inline_serializer(
            name="OwnerReviewReplyForbidden",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def owner_review_reply(request, review_id):
    """Соҳиби ҷой ё админи ваколатдор ба отзыв ҷавоб медиҳад."""

    user = request.user

    if not user.is_active or getattr(user, "is_blocked", False):
        return Response(
            {"detail": "Аккаунти шумо фаъол нест."},
            status=status.HTTP_403_FORBIDDEN,
        )

    is_admin = (
        user.is_staff
        and (
            user.is_superuser
            or getattr(user, "role", "") == "admin"
        )
    )

    review = get_object_or_404(
        Review.objects.select_related("place"),
        id=review_id,
        status=Review.Status.APPROVED,
    )

    if review.place.owner_id != user.id and not is_admin:
        return Response(
            {"detail": "Шумо соҳиби ин ҷой нестед."},
            status=status.HTTP_403_FORBIDDEN,
        )

    reply = request.data.get("reply", "")

    if not isinstance(reply, str):
        return Response(
            {"detail": "Ҷавоб бояд матн бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reply = reply.strip()

    if not reply or len(reply) > 2000:
        return Response(
            {"detail": "Ҷавоб бояд аз 1 то 2000 аломат бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    review.owner_reply = reply
    review.owner_reply_at = timezone.now()
    review.save(
        update_fields=["owner_reply", "owner_reply_at", "updated_at"]
    )

    language = getattr(review.user, "language", "ru")

    messages = {
        "ru": (
            "Ответ владельца",
            "Владелец места ответил на ваш отзыв.",
        ),
        "tg": (
            "Ҷавоби соҳиби ҷой",
            "Соҳиби ҷой ба отзыви шумо ҷавоб дод.",
        ),
        "en": (
            "Owner reply",
            "The place owner replied to your review.",
        ),
    }

    title, message = messages.get(language, messages["ru"])

    Notification.objects.create(
        user=review.user,
        notification_type=Notification.Type.OWNER_REPLY,
        title=title,
        message=message,
        review=review,
    )


    return Response({
        "detail": "Ҷавоб сабт шуд.",
        "review_id": review.id,
        "owner_reply": review.owner_reply,
        "owner_reply_at": review.owner_reply_at,
    })



@extend_schema(
    summary="Эҷоди дархости тасдиқи соҳиби ҷой",
    request=ClaimCreateSerializer,
    responses={
        201: ClaimSerializer,
        400: inline_serializer(
            name="ClaimCreateBadRequest",
            fields={"detail": serializers.CharField()},
        ),
        403: inline_serializer(
            name="ClaimCreateForbidden",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def claim_create(request):
    if not request.user.is_active or request.user.is_blocked:
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ClaimCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    place = serializer.validated_data["place"]

    if Claim.objects.filter(
        place=place,
        user=request.user,
        status=Claim.Status.PENDING,
    ).exists():
        return Response(
            {"detail": "Шумо аллакай дархости интизорӣ доред."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    claim = serializer.save(user=request.user)

    return Response(
        ClaimSerializer(claim).data,
        status=status.HTTP_201_CREATED,
    )



@extend_schema(
    summary="Рӯйхати дархостҳои тасдиқи соҳиби ҷой",
    parameters=[
        OpenApiParameter(
            name="status",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=list(Claim.Status.values),
            description="Филтр аз рӯйи ҳолати дархост",
        ),
    ],
    responses={
        200: ClaimSerializer(many=True),
    },
)
@api_view(["GET"])
@permission_classes([IsPlacewiseAdmin])
def admin_claim_list(request):
    claims = Claim.objects.select_related(
        "place", "user"
    ).all()

    claim_status = request.query_params.get("status")

    if claim_status in Claim.Status.values:
        claims = claims.filter(status=claim_status)

    return Response(ClaimSerializer(claims, many=True).data)



@extend_schema(
    summary="Баррасии дархости соҳиби ҷой",
    request=inline_serializer(
        name="AdminClaimReviewRequest",
        fields={
            "action": serializers.ChoiceField(
                choices=["approve", "reject"],
            ),
            "reason": serializers.CharField(
                required=False,
                allow_blank=True,
            ),
        },
    ),
    responses={
        200: inline_serializer(
            name="AdminClaimReviewResponse",
            fields={
                "detail": serializers.CharField(),
                "claim_id": serializers.IntegerField(),
                "status": serializers.CharField(),
                "reason": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="AdminClaimReviewBadRequest",
            fields={"detail": serializers.CharField()},
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_claim_review(request, claim_id):
    action = request.data.get("action")
    reason = str(request.data.get("reason", "")).strip()

    if action not in ("approve", "reject"):
        return Response(
            {"detail": "action бояд approve ё reject бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if action == "reject" and not reason:
        return Response(
            {"detail": "Барои рад кардан reason ҳатмист."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        claim = get_object_or_404(
            Claim.objects.select_for_update().select_related("place"),
            pk=claim_id,
        )

        if claim.status != Claim.Status.PENDING:
            return Response(
                {"detail": "Ин дархост аллакай баррасӣ шудааст."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if action == "approve":
            claim.place.owner = claim.user
            claim.place.save(
                update_fields=["owner", "updated_at"]
            )

            claim.user.role = claim.user.Role.OWNER
            claim.user.save(update_fields=["role"])

            claim.status = Claim.Status.APPROVED
        else:
            claim.status = Claim.Status.REJECTED

        claim.save(update_fields=["status"])

    return Response({
        "detail": (
            "Дархост тасдиқ шуд."
            if action == "approve"
            else "Дархост рад шуд."
        ),
        "claim_id": claim.id,
        "status": claim.status,
        "reason": reason if action == "reject" else "",
    })




@extend_schema(
    tags=["Uploads"],
    summary="Бор кардани акс",
    description="JPG, PNG ё WebP, андозаи максималӣ 10 MB.",
    request=inline_serializer(
        name="UploadImageRequest",
        fields={
            "file": serializers.ImageField(),
        },
    ),
    
    responses={
        201: inline_serializer(
            name="UploadImageResponse",
            fields={
                "url": serializers.URLField(),
                "filename": serializers.CharField(),
                "size": serializers.IntegerField(),
                "format": serializers.CharField(),
            },
        ),
        400: inline_serializer(
            name="UploadImageError",
            fields={
                "detail": serializers.CharField(),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_image(request):
    if not request.user.is_active or request.user.is_blocked:
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    uploaded_file = request.FILES.get("file")

    if not uploaded_file:
        return Response(
            {"detail": "Файли file ҳатмист."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded_file.size > 10 * 1024 * 1024:
        return Response(
            {"detail": "Акс набояд аз 10 MB зиёд бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        image = Image.open(uploaded_file)
        image_format = image.format
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return Response(
            {"detail": "Файли фиристодашуда акси дуруст нест."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    extensions = {
        "JPEG": "jpg",
        "PNG": "png",
        "WEBP": "webp",
    }

    if image_format not in extensions:
        return Response(
            {"detail": "Танҳо JPG, PNG ва WebP иҷозатанд."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    extension = extensions[image_format]
    path = default_storage.save(
        f"uploads/{uuid4().hex}.{extension}",
        uploaded_file,
    )

    return Response(
        {
            "url": request.build_absolute_uri(
                default_storage.url(path)
            ),
            "filename": path.rsplit("/", 1)[-1],
            "size": uploaded_file.size,
            "format": image_format.lower(),
        },
        status=status.HTTP_201_CREATED,
    )



@extend_schema(
    summary="Нашр кардани ҷой",
    request=None,
    responses={
        200: inline_serializer(
            name="AdminPlacePublishResponse",
            fields={
                "detail": serializers.CharField(),
                "id": serializers.IntegerField(required=False),
                "name": serializers.CharField(required=False),
                "status": serializers.CharField(required=False),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_place_publish(request, place_id):
    """Нашр кардани ҷой аз ҷониби администратор."""

    place = get_object_or_404(Place, id=place_id)

    if place.status == Place.Status.PUBLISHED:
        return Response({
            "detail": "Ин ҷой аллакай нашр шудааст."
        })

    place.status = Place.Status.PUBLISHED
    place.save(update_fields=["status", "updated_at"])

    return Response({
        "detail": "Ҷой бомуваффақият нашр шуд.",
        "id": place.id,
        "name": place.name,
        "status": place.status,
    })



@extend_schema(
    summary="Пинҳон кардани ҷой",
    request=None,
    responses={
        200: inline_serializer(
            name="AdminPlaceHideResponse",
            fields={
                "detail": serializers.CharField(),
                "id": serializers.IntegerField(required=False),
                "name": serializers.CharField(required=False),
                "status": serializers.CharField(required=False),
            },
        ),
    },
)
@api_view(["POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_place_hide(request, place_id):
    place = get_object_or_404(Place, id=place_id)

    if place.status == Place.Status.HIDDEN:
        return Response({"detail": "Ин ҷой аллакай пинҳон аст."})

    place.status = Place.Status.HIDDEN
    place.save(update_fields=["status", "updated_at"])

    return Response({
        "detail": "Ҷой бомуваффақият пинҳон шуд.",
        "id": place.id,
        "name": place.name,
        "status": place.status,
    })



@extend_schema(
    parameters=[
        OpenApiParameter(
            name="status",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            enum=["draft", "published", "hidden"],
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Ҷустуҷӯ аз рӯйи номи ҷой",
        ),
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
        ),
    ],
    responses=inline_serializer(
        name="AdminPlacesPaginatedResponse",
        fields={
            "count": serializers.IntegerField(),
            "next": serializers.URLField(
                allow_null=True,
            ),
            "previous": serializers.URLField(
                allow_null=True,
            ),
            "results": PlaceListSerializer(many=True),
        },
    ),
)
@api_view(["GET"])
@permission_classes([IsPlacewiseAdmin])
def admin_places_list(request):
    places = Place.objects.all()

    status_filter = request.query_params.get("status")
    search = request.query_params.get("search")

    if status_filter in ["draft", "published", "hidden"]:
        places = places.filter(status=status_filter)

    if search:
        places = places.filter(
            Q(name__icontains=search)
        )

    paginator = AdminPlacePagination()
    page = paginator.paginate_queryset(places, request)

    serializer = PlaceListSerializer(
        page,
        many=True,
        context={"request": request},
    )

    return paginator.get_paginated_response(serializer.data)




class AdminPlacePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100



@extend_schema(
    summary="Таҳрири ҷой аз ҷониби администратор",
    request=AdminPlaceUpdateSerializer,
    responses={
        200: inline_serializer(
            name="AdminPlaceUpdateResponse",
            fields={
                "detail": serializers.CharField(),
                "id": serializers.IntegerField(),
                "name": serializers.CharField(),
                "status": serializers.CharField(),
            },
        ),
    },
)
@api_view(["PATCH"])
@permission_classes([IsPlacewiseAdmin])
def admin_place_update(request, place_id):
    place = get_object_or_404(Place, id=place_id)

    serializer = AdminPlaceUpdateSerializer(
        place,
        data=request.data,
        partial=True,
    )

    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response({
        "detail": "Маълумоти ҷой нав карда шуд.",
        "id": place.id,
        "name": place.name,
        "status": place.status,
    })

