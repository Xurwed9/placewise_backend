from django.core.files.storage import default_storage
from rest_framework.decorators import parser_classes
from rest_framework.parsers import (
    MultiPartParser,
    FormParser,
    JSONParser,
)
from django.db.models import Q, TextField, Count
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from core.pagination import StandardPagination
from rest_framework.response import Response
from django.contrib.gis.geos import Polygon
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes,extend_schema_view, OpenApiResponse,OpenApiRequest
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsPlacewiseAdmin
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
from zoneinfo import ZoneInfo

from .models import Category, Place,Favorite,Claim, PlacePhoto
from .serializers import (
    CategorySerializer,
    PlaceListSerializer,
    PlaceMapPointSerializer,
    PlaceDetailSerializer,
    FavoriteSerializer,
    PlacePaginationSerializer,
    OwnerPlaceUpdateSerializer, ClaimCreateSerializer,
    ClaimSerializer, AdminPlaceUpdateSerializer, AdminCategorySerializer,
    AdminPlaceSerializer, PlacePhotoSerializer, map_place_status,
)
from reviews.models import Review
from reviews.serializers import ReviewSerializer
from notifications.models import Notification
from core.hours import is_open_now
from core.image_processing import process_uploaded_image_variants

import hashlib
from django.core.cache import cache



def _delete_place_photo_files(photo):
    if photo.image:
        photo.image.delete(save=False)

    if photo.thumbnail:
        photo.thumbnail.delete(save=False)


def _is_favorite_for_slug(request, slug):
    user = getattr(request, "user", None)

    if user is None or not user.is_authenticated:
        return False

    return Favorite.objects.filter(
        user=user,
        place__slug=slug,
    ).exists()


def _public_api_cache_key(request, endpoint):

    accept_language = request.headers.get("Accept-Language", "")

    cache_version = cache.get("public-api-version", 1)

    raw_key = (
        f"{endpoint}:"
        f"{cache_version}:"
        f"{request.get_full_path()}:"
        f"{accept_language}"
    )

    digest = hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()

    return f"public-api:{digest}"


class PlacePagination(StandardPagination):
    pass




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
            description="Радиуси ҷустуҷӯ бо метр; аз 100 то 100000",
        ),
        OpenApiParameter(
            name="radius_m",
            type=float,
            location=OpenApiParameter.QUERY,
            description="Радиуси ҷустуҷӯ бо метр; аз 100 то 100000",
        ),
        OpenApiParameter(
            name="radius_km",
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
            name="limit",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Алиаси page_size, ҳадди аксар 100",
        ),
        OpenApiParameter(
            name="search",
            type=str,
            location=OpenApiParameter.QUERY,
            description="Ҷустуҷӯ аз рӯйи ном, суроға, slug ё ноҳия",
        ),
        OpenApiParameter(
            name="q",
            type=str,
            location=OpenApiParameter.QUERY,
            description="Алиаси search",
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
            name="rating_min",
            type=float,
            location=OpenApiParameter.QUERY,
            description="Алиаси min_rating",
        ),
        OpenApiParameter(
            name="price_level",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Сатҳи нарх аз 1 то 4",
        ),
        OpenApiParameter(
            name="price",
            type=int,
            location=OpenApiParameter.QUERY,
            description="Алиаси price_level",
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
        OpenApiParameter(
            name="sort",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=["best", "rating", "reviews", "distance"],
            description="Тартиби навъбандӣ аз рӯйи ТЗ",
        ),
    ],
)
@api_view(["GET"])
def place_list(request):
    cache_key = _public_api_cache_key(
        request,
        "place-list",
    )

    cached_data = cache.get(cache_key)

    if cached_data is not None:
        return Response(cached_data)
    places = (
        Place.objects
        .filter(status=Place.Status.PUBLISHED)
        .select_related("category", "brand")
    )

    search = (
        request.query_params.get("q")
        or request.query_params.get("search", "")
    ).strip()

    if search:
        places = places.annotate(
            name_text=Cast("name", output_field=TextField()),
            address_text=Cast("address", output_field=TextField()),
            subcategory_text=Cast(
                "subcategory",
                output_field=TextField(),
            ),
        )

        search_filter = (
            Q(name_text__icontains=search)
            | Q(address_text__icontains=search)
            | Q(subcategory_text__icontains=search)
            | Q(slug__icontains=search)
            | Q(district__icontains=search)
        )

        # pg_trgm improves matching for typos while keeping exact substring
        # behaviour for short queries.
        if len(search) >= 3:
            places = places.annotate(
                name_similarity=TrigramSimilarity("name_text", search),
                address_similarity=TrigramSimilarity(
                    "address_text",
                    search,
                ),
                subcategory_similarity=TrigramSimilarity(
                    "subcategory_text",
                    search,
                ),
            )

            search_filter |= (
                Q(name_similarity__gt=0.2)
                | Q(address_similarity__gt=0.2)
                | Q(subcategory_similarity__gt=0.2)
            )

        places = places.filter(search_filter)

    category = request.query_params.get("category", "").strip()

    if category:
        places = places.filter(
            Q(category__slug=category)
            | Q(category__key=category)
        )

    district = request.query_params.get("district", "").strip()

    if district:
        places = places.filter(district__icontains=district)

    min_rating = (
        request.query_params.get("rating_min")
        or request.query_params.get("min_rating")
    )

    if min_rating not in (None, ""):
        try:
            rating_value = float(min_rating)

            if not 0 <= rating_value <= 5:
                raise ValueError

        except (ValueError, TypeError):
            return Response(
                {"error": "rating_min бояд аз 0 то 5 бошад"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        places = places.filter(rating__gte=rating_value)

    price_level = (
        request.query_params.get("price")
        or request.query_params.get("price_level")
    )

    if price_level not in (None, ""):
        try:
            price_value = int(price_level)

            if price_value not in {1, 2, 3, 4}:
                raise ValueError

        except (ValueError, TypeError):
            return Response(
                {
                    "error": (
                        "price бояд адади бутун "
                        "аз 1 то 4 бошад"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        places = places.filter(price_level=price_value)

    lat = request.query_params.get("lat")
    lon = request.query_params.get("lon")
    radius_m = request.query_params.get("radius_m")
    radius_km = request.query_params.get("radius_km")
    radius = request.query_params.get("radius")
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

            if radius_m not in (None, ""):
                radius_km_value = float(radius_m) / 1000
            elif radius_km not in (None, ""):
                radius_km_value = float(radius_km)
            elif radius not in (None, ""):
                radius_km_value = float(radius) / 1000
            else:
                radius_km_value = 5

            if not -90 <= lat_value <= 90:
                raise ValueError

            if not -180 <= lon_value <= 180:
                raise ValueError

            if not 0.1 <= radius_km_value <= 100:
                raise ValueError

        except (ValueError, TypeError):
            return Response(
                {
                    "error": (
                        "lat, lon ё radius нодуруст аст. "
                        "radius бояд аз 100 то 100000 метр бошад."
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
                D(km=radius_km_value),
            ),
        )

    if open_now not in (None, ""):
        if open_now.lower() not in {"true", "false"}:
            return Response(
                {"error": "open_now бояд true ё false бошад"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now().astimezone(ZoneInfo("Asia/Dushanbe"))
        matching_ids = []

        for place in places.iterator():
            is_open = is_open_now(place.opening_hours, now)

            if is_open is None:
                continue

            if is_open == (open_now.lower() == "true"):
                matching_ids.append(place.id)

        places = places.filter(id__in=matching_ids)

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
    sort = request.query_params.get("sort")

    if sort not in (None, ""):
        sort_map = {
            "best": "-rating",
            "rating": "-rating",
            "reviews": "-reviews_count",
            "distance": "distance",
        }
        ordering = sort_map.get(sort)

        if ordering is None:
            return Response(
                {
                    "error": "sort нодуруст аст",
                    "allowed": sorted(sort_map),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        ordering = request.query_params.get("ordering", "-rating")

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
                        "Барои sort=distance "
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

    paginator = PlacePagination()
    page = paginator.paginate_queryset(places, request)

    serializer = PlaceListSerializer(
        page,
        many=True,
        context={"request": request},
    )

    response = paginator.get_paginated_response(
        serializer.data
    )

    cache.set(
        cache_key,
        response.data,
        timeout=30,
    )

    return response




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
    cache_key = _public_api_cache_key(
        request,
        "place-detail",
    )

    cached_data = cache.get(cache_key)

    if cached_data is not None:
        data = dict(cached_data)
        data["is_favorite"] = _is_favorite_for_slug(request, slug)
        return Response(data)
    place = get_object_or_404(
        Place.objects
        .filter(status=Place.Status.PUBLISHED)
        .select_related("category", "brand")
        .prefetch_related("photos"),
        slug=slug,
    )

    serializer = PlaceDetailSerializer(
        place,
        context={
            "request": request,
            "skip_favorite": True,
        },
    )

    data = serializer.data

    cache.set(
        cache_key,
        data,
        timeout=30,
    )

    data = dict(data)
    data["is_favorite"] = _is_favorite_for_slug(request, slug)

    return Response(data)





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
                "results": PlaceMapPointSerializer(many=True),
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

    serializer = PlaceMapPointSerializer(
        places,
        many=True,
        context={"request": request},
    )

    data = serializer.data
    total = places.count()

    return Response({
        "count": total,
        "total": total,
        "results": data,
        "items": data,
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
    )

    if place.location is not None:
        similar = (
            similar
            .filter(location__isnull=False)
            .annotate(distance=Distance("location", place.location))
            .order_by("distance", "-rating", "-reviews_count")
        )
    else:
        similar = similar.order_by("-rating", "-reviews_count")

    similar = similar[:6]

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



def _favorite_list_impl(request):
    if request.method == "GET":
        favorites = (
            Favorite.objects
            .filter(user=request.user)
            .select_related("place")
        )

        pagination_requested = any(
            key in request.query_params
            for key in ("page", "limit", "page_size")
        )

        serializer_context = {
            "request": request,
            "language": request.query_params.get("lang", "ru"),
        }

        if pagination_requested:
            paginator = StandardPagination()
            page = paginator.paginate_queryset(favorites, request)
            serializer = FavoriteSerializer(
                page,
                many=True,
                context=serializer_context,
            )
            return paginator.get_paginated_response(serializer.data)

        serializer = FavoriteSerializer(
            favorites,
            many=True,
            context=serializer_context,
        )
        return Response(serializer.data)

    if request.method == "DELETE":
        place_id = (
            request.data.get("place")
            or request.data.get("place_id")
            or request.query_params.get("place")
            or request.query_params.get("place_id")
        )

        if not place_id:
            return Response(
                {"error": "place ё place_id лозим аст"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        favorite = get_object_or_404(
            Favorite,
            user=request.user,
            place_id=place_id,
        )
        favorite.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    place_id = (
        request.data.get("place")
        or request.data.get("place_id")
    )

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
    methods=["GET"],
    operation_id="me_favorites_list",
    responses={200: FavoriteSerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    operation_id="me_favorites_create",
    request=FavoriteSerializer,
    responses={201: FavoriteSerializer, 200: FavoriteSerializer},
)
@extend_schema(
    methods=["DELETE"],
    operation_id="me_favorites_remove",
    request=None,
    parameters=[
        OpenApiParameter(
            name="place_id",
            type=int,
            location=OpenApiParameter.QUERY,
            required=True,
            description="ID-и ҷойе, ки аз Favorites нест карда мешавад",
        ),
    ],
    responses={
        204: None,
        400: OpenApiTypes.OBJECT,
        404: OpenApiTypes.OBJECT,
    },
)
@api_view(["GET", "POST", "DELETE"])
@permission_classes([IsAuthenticated])
def me_favorite_list(request):
    return _favorite_list_impl(request)


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
        .order_by("-rating", "-reviews_count")[:4]
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
        .order_by("sort_order", "id")[:4]
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
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "results": PlaceDetailSerializer(many=True),
                "items": PlaceDetailSerializer(many=True),
                "total": serializers.IntegerField(),
                "page": serializers.IntegerField(),
                "limit": serializers.IntegerField(),
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

    paginator = StandardPagination()
    page = paginator.paginate_queryset(places, request)
    serializer = PlaceDetailSerializer(
        page,
        many=True,
        context={"request": request},
    )

    return paginator.get_paginated_response(serializer.data)



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
@parser_classes([MultiPartParser, FormParser, JSONParser])
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

    photo_files = serializer.validated_data.pop("photos", [])
    remove_photo_ids = serializer.validated_data.pop(
        "remove_photo_ids",
        [],
    )

    try:
        with transaction.atomic():
            serializer.save()

            if remove_photo_ids:
                photos_to_delete = list(
                    place.photos.filter(id__in=remove_photo_ids)
                )
                for photo in photos_to_delete:
                    _delete_place_photo_files(photo)
                place.photos.filter(id__in=remove_photo_ids).delete()

            for uploaded_file in photo_files:
                variants = process_uploaded_image_variants(
                    uploaded_file
                )
                PlacePhoto.objects.create(
                    place=place,
                    author=request.user,
                    source=PlacePhoto.Source.OWNER,
                    image=variants["image"],
                    thumbnail=variants["thumbnail"],
                )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

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
def claim_create(request, slug=None):
    if not request.user.is_active or request.user.is_blocked:
        return Response(
            {"detail": "Дастрасӣ манъ аст."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if slug is None:
        return Response(
            {"detail": "Slug-и ҷой талаб карда мешавад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    place = get_object_or_404(
        Place,
        slug=slug,
        status=Place.Status.PUBLISHED,
    )

    serializer = ClaimCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    if Claim.objects.filter(
        place=place,
        user=request.user,
        status=Claim.Status.PENDING,
    ).exists():
        return Response(
            {"detail": "Шумо аллакай дархости интизорӣ доред."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    claim = serializer.save(user=request.user, place=place)

    return Response(
        ClaimSerializer(claim).data,
        status=status.HTTP_201_CREATED,
    )



@extend_schema(
    methods=["GET"],
    operation_id="admin_claim_list",
    summary="Рӯйхати дархостҳои тасдиқи соҳиби ҷой",
    parameters=[
        OpenApiParameter(
            name="status",
            type=str,
            location=OpenApiParameter.QUERY,
            enum=list(Claim.Status.values),
            description="Филтр аз рӯйи ҳолати дархост",
        ),
        OpenApiParameter("page", int),
        OpenApiParameter("limit", int),
    ],
    responses={
        200: inline_serializer(
            name="AdminClaimPaginatedResponse",
            fields={
                "count": serializers.IntegerField(),
                "next": serializers.URLField(allow_null=True),
                "previous": serializers.URLField(allow_null=True),
                "results": ClaimSerializer(many=True),
                "items": ClaimSerializer(many=True),
                "total": serializers.IntegerField(),
                "page": serializers.IntegerField(),
                "limit": serializers.IntegerField(),
            },
        ),
    },
)
@extend_schema(
    methods=["POST"],
    operation_id="admin_claim_action",
    summary="Тасдиқ ё рад кардани дархости соҳиби ҷой",
    request=inline_serializer(
        name="AdminClaimActionRequest",
        fields={
            "claim_id": serializers.IntegerField(),
            "action": serializers.ChoiceField(
                choices=["approve", "reject"],
            ),
            "reason": serializers.CharField(
                required=False,
                allow_blank=True,
            ),
        },
    ),
    responses={200: dict, 400: dict, 404: dict},
)
@api_view(["GET", "POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_claim_list(request):
    if request.method == "POST":
        claim_id = (
            request.data.get("claim_id")
            or request.data.get("id")
        )

        if not claim_id:
            return Response(
                {"error": "claim_id лозим аст"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _admin_claim_review_impl(request, claim_id)

    claims = Claim.objects.select_related(
        "place", "user"
    ).all()

    claim_status = request.query_params.get("status")

    if claim_status in Claim.Status.values:
        claims = claims.filter(status=claim_status)

    paginator = StandardPagination()
    page = paginator.paginate_queryset(claims, request)

    return paginator.get_paginated_response(
        ClaimSerializer(page, many=True).data
    )



def _admin_claim_review_impl(request, claim_id, forced_action=None):
    action = forced_action or request.data.get("action")
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

    uploaded_file = request.FILES.get("file") or request.FILES.get("image")

    if not uploaded_file:
        return Response(
            {"detail": "Файли file ё image ҳатмист."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        variants = process_uploaded_image_variants(uploaded_file)
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    image_path = default_storage.save(
        f"uploads/{variants['image'].name}",
        variants["image"],
    )

    thumbnail_path = default_storage.save(
        f"uploads/thumbnails/{variants['thumbnail'].name}",
        variants["thumbnail"],
    )

    return Response(
        {
            "url": request.build_absolute_uri(
                default_storage.url(image_path)
            ),
            "thumbnail_url": request.build_absolute_uri(
                default_storage.url(thumbnail_path)
            ),
            "filename": image_path.rsplit("/", 1)[-1],
            "format": "webp",
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
        "status": map_place_status(place.status),
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
        "status": map_place_status(place.status),
    })




@extend_schema(
    request=AdminPlaceSerializer,
    responses={201: AdminPlaceSerializer},
)
@api_view(["GET", "POST"])
@permission_classes([IsPlacewiseAdmin])
def admin_places_list(request):
    if request.method == "POST":
        serializer = AdminPlaceSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        place = serializer.save()

        return Response(
            AdminPlaceSerializer(
                place,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    places = Place.objects.all()

    status_filter = request.query_params.get("status")
    search = request.query_params.get("search")

    status_map = {
        "active": [Place.Status.PUBLISHED],
        "published": [Place.Status.PUBLISHED],
        "hidden": [Place.Status.HIDDEN, Place.Status.DRAFT],
        "draft": [Place.Status.DRAFT],
        "closed": [Place.Status.CLOSED],
    }

    if status_filter in status_map:
        places = places.filter(status__in=status_map[status_filter])

    if search:
        places = places.filter(Q(name__icontains=search))

    paginator = AdminPlacePagination()
    page = paginator.paginate_queryset(places, request)

    serializer = PlaceListSerializer(
        page,
        many=True,
        context={"request": request},
    )

    return paginator.get_paginated_response(serializer.data)





@extend_schema_view(
    get=extend_schema(
        operation_id="admin_place_detail",
        responses=AdminPlaceSerializer,
    ),
    patch=extend_schema(
        operation_id="admin_place_update",
        request=AdminPlaceSerializer,
        responses=AdminPlaceSerializer,
    ),
    delete=extend_schema(
        operation_id="admin_place_delete",
        responses={204: None, 409: OpenApiResponse(description="Place has reviews")},
    ),
)
@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsPlacewiseAdmin])
def admin_place_update(request, place_id):
    place = get_object_or_404(Place, id=place_id)

    if request.method == "GET":
        serializer = AdminPlaceSerializer(
            place,
            context={"request": request},
        )
        return Response(serializer.data)

    if request.method == "PATCH":
        serializer = AdminPlaceSerializer(
            place,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    if Review.objects.filter(place=place).exists():
        return Response(
            {
                "detail": (
                    "Ин ҷой review дорад. "
                    "Барои нигоҳ доштани таърихи review "
                    "онро нест кардан мумкин нест."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )


    photos = list(place.photos.all())

    place.delete()

    for photo in photos:
        _delete_place_photo_files(photo)

    return Response(status=status.HTTP_204_NO_CONTENT)



class AdminPlacePagination(PlacePagination):
    pass



@extend_schema(
    methods=["GET"],
    operation_id="admin_category_list",
    responses={200: AdminCategorySerializer(many=True)},
)
@extend_schema(
    methods=["POST"],
    operation_id="admin_category_create",
    request={"multipart/form-data": AdminCategorySerializer},
    responses={201: AdminCategorySerializer},
)
@api_view(["GET", "POST"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([IsPlacewiseAdmin])
def admin_categories(request):
    if request.method == "GET":
        categories = Category.objects.all().order_by(
            "sort_order", "id"
        )
        serializer = AdminCategorySerializer(
            categories,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    serializer = AdminCategorySerializer(
        data=request.data,
        context={"request": request},
    )

    if serializer.is_valid():
        category = serializer.save()
        return Response(
            AdminCategorySerializer(
                category,
                context={"request": request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    return Response(
        serializer.errors,
        status=status.HTTP_400_BAD_REQUEST,
    )




@extend_schema(
    methods=["GET"],
    operation_id="admin_category_detail",
    responses={200: AdminCategorySerializer},
)
@extend_schema(
    methods=["PATCH"],
    operation_id="admin_category_update",
    request={"multipart/form-data": AdminCategorySerializer},
    responses={200: AdminCategorySerializer},
)
@extend_schema(
    methods=["DELETE"],
    operation_id="admin_category_delete",
    responses={204: None},
)
@api_view(["GET", "PATCH", "DELETE"])
@parser_classes([JSONParser, MultiPartParser, FormParser])
@permission_classes([IsPlacewiseAdmin])
def admin_category_detail(request, category_id):
    category = get_object_or_404(
        Category,
        id=category_id,
    )

    if request.method == "GET":
        serializer = AdminCategorySerializer(
            category,
            context={"request": request},
        )
        return Response(serializer.data)

    if request.method == "PATCH":
        serializer = AdminCategorySerializer(
            category,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST,
        )

    # DELETE
    if Place.objects.filter(category=category).exists():
        return Response(
            {
                "detail": (
                    "Ин категория истифода мешавад. "
                    "Аввал ҷойҳои вобастаро ба категорияи дигар гузаронед."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )

    if category.image:
        category.image.delete(save=False)

    category.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)




@extend_schema(
    request={"multipart/form-data": PlacePhotoSerializer},
    responses={
        200: PlacePhotoSerializer(many=True),
        201: PlacePhotoSerializer,
    },
)
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsPlacewiseAdmin])
def admin_place_photos(request, place_id):
    place = get_object_or_404(Place, id=place_id)

    if request.method == "GET":
        photos = place.photos.all()
        serializer = PlacePhotoSerializer(
            photos,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    serializer = PlacePhotoSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(
        place=place,
        author=request.user,
        source=request.data.get(
            "source",
            PlacePhoto.Source.GIS_2GIS,
        ),
    )

    return Response(serializer.data, status=status.HTTP_201_CREATED)



def _owner_can_manage(user, place):
    if user.is_active is False or getattr(user, "is_blocked", False):
        return False

    if user.is_staff and (
        user.is_superuser or getattr(user, "role", "") == "admin"
    ):
        return True

    return place.owner_id == user.id


@extend_schema(
    tags=["Owner - Photos"],
    methods=["GET"],
    operation_id="owner_place_photos_list",
    responses={200: PlacePhotoSerializer(many=True)},
)
@extend_schema(
    tags=["Owner - Photos"],
    methods=["POST"],
    operation_id="owner_place_photos_create",
    request={"multipart/form-data": PlacePhotoSerializer},
    responses={201: PlacePhotoSerializer},
)
@api_view(["GET", "POST"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])
def owner_place_photos(request, place_id):
    place = get_object_or_404(Place, id=place_id)

    if not _owner_can_manage(request.user, place):
        return Response(
            {"detail": "Шумо соҳиби ин ҷой нестед."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        serializer = PlacePhotoSerializer(
            place.photos.all(),
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    serializer = PlacePhotoSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save(
        place=place,
        author=request.user,
        source=PlacePhoto.Source.OWNER,
    )

    return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(
    tags=["Owner - Photos"],
    methods=["PATCH"],
    operation_id="owner_place_photo_update",
    request={"multipart/form-data": PlacePhotoSerializer},
    responses={200: PlacePhotoSerializer},
)
@extend_schema(
    tags=["Owner - Photos"],
    methods=["DELETE"],
    operation_id="owner_place_photo_delete",
    responses={204: None},
)
@api_view(["PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsAuthenticated])

def owner_photo_detail(request, place_id, photo_id):
    place = get_object_or_404(Place, id=place_id)

    if not _owner_can_manage(request.user, place):
        return Response(
            {"detail": "Шумо соҳиби ин ҷой нестед."},
            status=status.HTTP_403_FORBIDDEN,
        )

    photo = get_object_or_404(
        PlacePhoto.objects.select_related("place"),
        id=photo_id,
        place_id=place_id,
    )

    if request.method == "PATCH":
        serializer = PlacePhotoSerializer(
            photo,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    _delete_place_photo_files(photo)
    photo.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)



@extend_schema(
request=PlacePhotoSerializer,
responses={200: PlacePhotoSerializer, 204: None},
)
@api_view(["PATCH", "DELETE"])
@parser_classes([MultiPartParser, FormParser])
@permission_classes([IsPlacewiseAdmin])
def admin_photo_detail(request, photo_id):
    photo = get_object_or_404(PlacePhoto, id=photo_id)

    if request.method == "PATCH":
        serializer = PlacePhotoSerializer(
            photo,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    _delete_place_photo_files(photo)
    photo.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)
