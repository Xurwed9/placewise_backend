from rest_framework.pagination import PageNumberPagination
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from drf_spectacular.utils import extend_schema_field

from .models import Category, Brand, Place, PlacePhoto, Favorite


SUPPORTED_LANGUAGES = {"ru", "tg", "en"}


def get_language(context):
    request = context.get("request")

    if request is None:
        return "ru"

    language = request.query_params.get("lang", "").lower()

    if language in SUPPORTED_LANGUAGES:
        return language

    accept_language = request.headers.get("Accept-Language", "")

    for item in accept_language.split(","):
        candidate = item.split(";")[0].strip().lower()
        candidate = candidate.split("-")[0]

        if candidate in SUPPORTED_LANGUAGES:
            return candidate

    return "ru"


def translate_json(value, language):
    """Танҳо JSON-и бисёрзабонаро ба як забон табдил медиҳад."""
    if not isinstance(value, dict):
        return value

    language_keys = {"ru", "tg", "en"}

    if not language_keys.intersection(value.keys()):
        return value

    return (
        value.get(language)
        or value.get("ru")
        or next(
            (item for item in value.values() if item),
            "",
        )
    )


class TranslatedSerializerMixin:
    def translated(self, value):
        language = get_language(self.context)
        return translate_json(value, language)


class CategorySerializer(
    TranslatedSerializerMixin,
    serializers.ModelSerializer,
):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon"]

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj):
        return self.translated(obj.name)



class BrandSerializer(
    TranslatedSerializerMixin,
    serializers.ModelSerializer,
):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "branches_count"]

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj):
        return self.translated(obj.name)

class PlacePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlacePhoto
        fields = ["id", "image", "alt", "sort_order", "is_cover"]


class PlaceListSerializer(
    TranslatedSerializerMixin,
    serializers.ModelSerializer,
):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)

    name = serializers.SerializerMethodField()
    subcategory = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    location = GeometryField(read_only=True)

    class Meta:
        model = Place
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "brand",
            "subcategory",
            "address",
            "district",
            "location",
            "rating",
            "reviews_count",
            "price_level",
            "status",
        ]

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj):
        return self.translated(obj.name)

    @extend_schema_field(serializers.CharField())
    def get_subcategory(self, obj):
        return self.translated(obj.subcategory)

    @extend_schema_field(serializers.CharField())
    def get_address(self, obj):
        return self.translated(obj.address)


class PlaceDetailSerializer(PlaceListSerializer):
    about = serializers.SerializerMethodField()
    opening_hours = serializers.SerializerMethodField()
    photos = PlacePhotoSerializer(many=True, read_only=True)

    class Meta(PlaceListSerializer.Meta):
        fields = PlaceListSerializer.Meta.fields + [
            "about",
            "phones",
            "website",
            "opening_hours",
            "ext_rating",
            "ext_reviews",
            "photos",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(serializers.CharField())
    def get_about(self, obj):
        return self.translated(obj.about)

    @extend_schema_field(serializers.CharField())
    def get_opening_hours(self, obj):
        return self.translated(obj.opening_hours)



class FavoriteSerializer(serializers.ModelSerializer):
    place_name = serializers.SerializerMethodField()
    place_slug = serializers.CharField(source="place.slug", read_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "place", "place_name", "place_slug", "created_at"]
        read_only_fields = ["id", "place_name", "place_slug", "created_at"]

    @extend_schema_field(serializers.CharField())
    def get_place_name(self, obj):
        language = self.context.get("language", "ru")
        name = obj.place.name

        if isinstance(name, dict):
            return (
                name.get(language)
                or name.get("ru")
                or next(iter(name.values()), "")
            )

        return name


class PlacePaginationSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = PlaceListSerializer(many=True)
