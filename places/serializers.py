from rest_framework.pagination import PageNumberPagination
from rest_framework import serializers
from rest_framework_gis.fields import GeometryField
from drf_spectacular.utils import extend_schema_field
from core.hours import format_hours_text, is_open_now, normalize_hours
from core.image_processing import process_uploaded_image_variants
from users.phone_utils import normalize_phone

from .models import Category, Brand, Place, PlacePhoto, Favorite, Claim


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
    place_count = serializers.IntegerField(read_only=True)
    sort = serializers.IntegerField(
        source="sort_order",
        read_only=True,
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "key",
            "slug",
            "icon",
            "image",
            "place_count",
            "sort",
            "sort_order",
        ]

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj):
        return self.translated(obj.name)


class BrandSerializer(
    TranslatedSerializerMixin,
    serializers.ModelSerializer,
):
    name = serializers.SerializerMethodField()
    branches = serializers.IntegerField(
        source="branches_count",
        read_only=True,
    )

    class Meta:
        model = Brand
        fields = [
            "id",
            "name",
            "slug",
            "branches",
            "branches_count",
            "logo",
            "website",
            "instagram",
        ]


    @extend_schema_field(serializers.CharField())
    def get_name(self, obj):
        return self.translated(obj.name)


class PlacePhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    sort = serializers.IntegerField(source="sort_order", read_only=True)

    class Meta:
        model = PlacePhoto
        fields = [
            "id",
            "url",
            "image",
            "thumbnail",
            "alt",
            "author_id",
            "source",
            "credit",
            "sort",
            "sort_order",
            "is_cover",
        ]
        read_only_fields = ["id", "url", "thumbnail", "author_id", "sort"]

    @extend_schema_field(serializers.URLField(allow_blank=True))
    def get_url(self, obj):
        if not obj.image:
            return ""

        try:
            url = obj.image.url
        except ValueError:
            return ""

        request = self.context.get("request")
        if request is not None:
            return request.build_absolute_uri(url)

        return url

    def create(self, validated_data):
        uploaded_image = validated_data.get("image")

        if uploaded_image:
            variants = process_uploaded_image_variants(
                uploaded_image
            )
            validated_data["image"] = variants["image"]
            validated_data["thumbnail"] = variants["thumbnail"]

        return super().create(validated_data)

    def update(self, instance, validated_data):
        uploaded_image = validated_data.get("image")

        if not uploaded_image:
            return super().update(instance, validated_data)

        variants = process_uploaded_image_variants(
            uploaded_image
        )

        old_image = instance.image
        old_thumbnail = instance.thumbnail

        validated_data["image"] = variants["image"]
        validated_data["thumbnail"] = variants["thumbnail"]

        instance = super().update(instance, validated_data)

        if old_image:
            old_image.delete(save=False)

        if old_thumbnail:
            old_thumbnail.delete(save=False)

        return instance

def map_place_status(status_value):
    if status_value == Place.Status.PUBLISHED:
        return "active"
    if status_value == Place.Status.CLOSED:
        return "closed"
    return "hidden"


class PlaceStatusField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        kwargs.setdefault(
            "choices",
            ["active", "hidden", "closed", "draft", "published"],
        )
        super().__init__(**kwargs)

    def to_representation(self, value):
        return map_place_status(value)

    def to_internal_value(self, data):
        mapping = {
            "active": Place.Status.PUBLISHED,
            "published": Place.Status.PUBLISHED,
            "hidden": Place.Status.HIDDEN,
            "closed": Place.Status.CLOSED,
            "draft": Place.Status.DRAFT,
        }
        value = mapping.get(data)

        if value is None:
            self.fail("invalid_choice", input=data)

        return value


class PlaceListSerializer(
    TranslatedSerializerMixin,
    serializers.ModelSerializer,
):
    category = CategorySerializer(read_only=True)
    brand = BrandSerializer(read_only=True)

    name = serializers.SerializerMethodField()
    subcategory = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    price = serializers.IntegerField(
        source="price_level",
        read_only=True,
    )
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()
    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
    )
    status = PlaceStatusField(read_only=True)
    status_tz = serializers.SerializerMethodField()
    status_internal = serializers.CharField(
        source="status",
        read_only=True,
    )
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
            "lat",
            "lon",
            "location",
            "rating",
            "reviews_count",
            "price",
            "price_level",
            "status",
            "status_tz",
            "status_internal",
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

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_lat(self, obj):
        return obj.location.y if obj.location else None

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_lon(self, obj):
        return obj.location.x if obj.location else None

    @extend_schema_field(serializers.ChoiceField(
        choices=["active", "hidden", "closed", "draft", "published"],
    ))
    def get_status_tz(self, obj):
        return map_place_status(obj.status)


class PlaceDetailSerializer(PlaceListSerializer):
    about = serializers.SerializerMethodField()
    ext_rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
        allow_null=True,
    )
    opening_hours = serializers.SerializerMethodField()
    hours = serializers.SerializerMethodField()
    hours_text = serializers.SerializerMethodField()
    open_now = serializers.SerializerMethodField()
    is_favorite = serializers.SerializerMethodField()
    photos = PlacePhotoSerializer(many=True, read_only=True)

    class Meta(PlaceListSerializer.Meta):
        fields = PlaceListSerializer.Meta.fields + [
            "about",
            "phones",
            "website",
            "opening_hours",
            "hours",
            "hours_text",
            "open_now",
            "is_favorite",
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

    @extend_schema_field(serializers.JSONField(allow_null=True))
    def get_hours(self, obj):
        value = getattr(obj, "opening_hours", None)
        normalized = normalize_hours(value)

        if normalized is not None:
            return normalized

        if isinstance(value, dict):
            return value.get("raw")

        if isinstance(value, str):
            return value

        return None

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_hours_text(self, obj):
        language = get_language(self.context)
        return format_hours_text(getattr(obj, "opening_hours", None), language)

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_open_now(self, obj):
        return is_open_now(getattr(obj, "opening_hours", None))

    @extend_schema_field(serializers.BooleanField())
    def get_is_favorite(self, obj):
        if self.context.get("skip_favorite"):
            return False

        request = self.context.get("request")
        user = getattr(request, "user", None)

        if user is None or not user.is_authenticated:
            return False

        return Favorite.objects.filter(user=user, place=obj).exists()


class PlaceMapPointSerializer(
    TranslatedSerializerMixin,
    serializers.ModelSerializer,
):
    name = serializers.SerializerMethodField()
    lat = serializers.SerializerMethodField()
    lon = serializers.SerializerMethodField()
    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
    )

    class Meta:
        model = Place
        fields = ["slug", "name", "lat", "lon", "rating"]

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj):
        return self.translated(obj.name)

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_lat(self, obj):
        return obj.location.y if obj.location else None

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_lon(self, obj):
        return obj.location.x if obj.location else None


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
    items = PlaceListSerializer(many=True)
    total = serializers.IntegerField()
    page = serializers.IntegerField()
    limit = serializers.IntegerField()



class OwnerPlaceUpdateSerializer(serializers.ModelSerializer):
    photos = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )
    remove_photo_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
    )
    hours = serializers.JSONField(
        required=False,
        write_only=True,
    )
    phone = serializers.CharField(
        required=False,
        allow_blank=False,
        write_only=True,
    )

    class Meta:
        model = Place
        fields = [
            "about",
            "phones",
            "phone",
            "website",
            "opening_hours",
            "hours",
            "photos",
            "remove_photo_ids",
        ]
    def to_internal_value(self, data):
        if hasattr(data, "copy"):
            data = data.copy()

        for field_name in (
            "about",
            "phones",
            "opening_hours",
            "hours",
            "phone",
            "website",
            "photos",
            "remove_photo_ids",
        ):
            if field_name in data and data[field_name] == "":
                data.pop(field_name)

        return super().to_internal_value(data)

    def validate_about(self, value):
        if isinstance(value, str):
            value = {"ru": value}

        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "about бояд object бо забонҳо ё матн бошад."
            )

        cleaned = {}
        for lang in ("ru", "tg", "en"):
            text = value.get(lang)
            if text in (None, ""):
                continue
            if not isinstance(text, str):
                raise serializers.ValidationError(
                    f"about.{lang} бояд матн бошад."
                )
            cleaned[lang] = text.strip()

        if not cleaned:
            raise serializers.ValidationError(
                "about наметавонад холӣ бошад."
            )

        return cleaned

    def validate_phones(self, value):
        if isinstance(value, str):
            value = [
                item
                for item in value.replace(";", ",").split(",")
                if item.strip()
            ]

        if not isinstance(value, list):
            raise serializers.ValidationError(
                "phones бояд рӯйхати рақамҳои телефон бошад."
            )

        if len(value) > 20:
            raise serializers.ValidationError(
                "На бештар аз 20 рақами телефон иҷозат аст."
            )

        normalized = []
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError(
                    "Ҳар як рақами телефон бояд матн бошад."
                )
            phone = normalize_phone(item)
            if phone is None:
                raise serializers.ValidationError(
                    f"Рақами телефон нодуруст аст: {item}"
                )
            if phone not in normalized:
                normalized.append(phone)

        return normalized

    def validate_phone(self, value):
        phone = normalize_phone(value)
        if phone is None:
            raise serializers.ValidationError(
                "Рақами телефон нодуруст аст."
            )
        return phone

    def validate_opening_hours(self, value):
        normalized = normalize_hours(value)
        if normalized is None:
            raise serializers.ValidationError(
                "opening_hours бояд вақти кушоишро дар формати дуруст дошта бошад."
            )
        return normalized

    def validate_hours(self, value):
        normalized = normalize_hours(value)
        if normalized is None:
            raise serializers.ValidationError(
                "hours бояд вақти кушоишро дар формати дуруст дошта бошад."
            )
        return normalized

    def validate(self, attrs):
        if "hours" in attrs:
            attrs["opening_hours"] = attrs.pop("hours")

        if "phone" in attrs:
            phone = attrs.pop("phone")
            phones = list(attrs.get("phones", self.instance.phones or []))
            if phone not in phones:
                phones.append(phone)
            attrs["phones"] = phones

        return attrs



class ClaimCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Claim
        fields = ["document_url"]


class ClaimSerializer(serializers.ModelSerializer):
    user_phone = serializers.CharField(
        source="user.phone",
        read_only=True,
    )
    place_slug = serializers.CharField(
        source="place.slug",
        read_only=True,
    )

    class Meta:
        model = Claim
        fields = [
            "id",
            "place",
            "place_slug",
            "user",
            "user_phone",
            "document_url",
            "status",
            "created_at",
        ]
        read_only_fields = fields



class AdminPlaceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "name",
            "slug",
            "category",
            "brand",
            "subcategory",
            "address",
            "district",
            "about",
            "phones",
            "website",
            "opening_hours",
            "price_level",
        ]



class AdminCategorySerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "key",
            "image",
            "icon",
            "is_active",
            "sort_order",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "name бояд object бо забонҳои ru, tg ва en бошад."
            )

        for lang in ("ru", "tg", "en"):
            if not isinstance(value.get(lang), str) or not value[lang].strip():
                raise serializers.ValidationError(
                    f"name.{lang} ҳатмӣ аст ва бояд матн бошад."
                )

        return {
            lang: value[lang].strip()
            for lang in ("ru", "tg", "en")
        }




class AdminPlaceSerializer(serializers.ModelSerializer):
    location = GeometryField(required=False, allow_null=True)
    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        coerce_to_string=False,
        read_only=True,
    )
    status = PlaceStatusField(required=False)
    status_tz = PlaceStatusField(source="status", required=False)
    status_internal = serializers.CharField(
        source="status",
        read_only=True,
    )

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
            "about",
            "phones",
            "website",
            "opening_hours",
            "price_level",
            "status",
            "status_tz",
            "status_internal",
            "source",
            "source_id",
            "rating",
            "reviews_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "rating",
            "reviews_count",
            "created_at",
            "updated_at",
        ]

    def validate_name(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "name бояд object бо забонҳои ru, tg ва en бошад."
            )

        for lang in ("ru", "tg", "en"):
            if not isinstance(value.get(lang), str) or not value[lang].strip():
                raise serializers.ValidationError(
                    f"name.{lang} ҳатмӣ аст."
                )

        return value

    def validate_address(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "address бояд object бо забонҳои ru, tg ва en бошад."
            )

        for lang in ("ru", "tg", "en"):
            if not isinstance(value.get(lang), str) or not value[lang].strip():
                raise serializers.ValidationError(
                    f"address.{lang} ҳатмӣ аст."
                )

        return value

    def validate(self, attrs):
        if self.instance is None:
            for field in ("name", "slug", "category", "address"):
                if field not in attrs:
                    raise serializers.ValidationError({
                        field: "Ин майдон ҳангоми сохтани ҷой ҳатмӣ аст."
                    })

        return attrs

