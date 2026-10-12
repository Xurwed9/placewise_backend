
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from django.contrib.gis.geos import Polygon
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.utils import inline_serializer
from rest_framework import serializers

from .models import Category, Place,Favorite
from .serializers import (
    CategorySerializer,
    PlaceListSerializer,
    PlaceDetailSerializer,
    FavoriteSerializer,
    PlacePaginationSerializer,
)


class PlacePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


@extend_schema(
    responses=CategorySerializer(many=True),
)
@api_view(["GET"])
def category_list(request):
    categories = Category.objects.filter(is_active=True)

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
                "created_at",
                "-created_at",
                "name",
                "-name",
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

    search = request.query_params.get("search")

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

    category = request.query_params.get("category")
    if category:
        places = places.filter(category__slug=category)

    district = request.query_params.get("district")
    if district:
        places = places.filter(district__icontains=district)

    min_rating = request.query_params.get("min_rating")
    if min_rating:
        try:
            rating_value = float(min_rating)
            if not 0 <= rating_value <= 5:
                raise ValueError
        except ValueError:
            return Response(
                {"error": "min_rating бояд аз 0 то 5 бошад"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        places = places.filter(rating__gte=rating_value)

    price_level = request.query_params.get("price_level")
    if price_level:
        try:
            price_value = int(price_level)
            if not 1 <= price_value <= 4:
                raise ValueError
        except ValueError:
            return Response(
                {"error": "price_level бояд адади бутун аз 1 то 4 бошад"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        places = places.filter(price_level=price_value)

    ordering = request.query_params.get("ordering", "-created_at")

    allowed_ordering = {
        "rating",
        "-rating",
        "created_at",
        "-created_at",
        "name",
        "-name",
    }

    if ordering not in allowed_ordering:
        return Response(
            {
                "error": "ordering нодуруст аст",
                "allowed": sorted(allowed_ordering),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if ordering in {"name", "-name"}:
        places = places.annotate(
            name_text=Cast("name", output_field=TextField())
        ).order_by(
            "-name_text" if ordering == "-name" else "name_text"
        )
    else:
        places = places.order_by(ordering)

    paginator = PlacePagination()
    page = paginator.paginate_queryset(places, request)

    serializer = PlaceListSerializer(page, many=True)

    return paginator.get_paginated_response(serializer.data)


@extend_schema(
    operation_id="place_detail",
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

    serializer = PlaceDetailSerializer(place)

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
        west, south, east, north = map(
            float,
            bbox.split(","),
        )

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

    area = Polygon.from_bbox(
        (west, south, east, north)
    )
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
    )

    return Response({
        "count": places.count(),
        "results": serializer.data,
    })




@extend_schema(
    operation_id="similar_places",
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
        .order_by("-rating", "-reviews_count")[:10]
    )

    serializer = PlaceListSerializer(
        similar,
        many=True,
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

