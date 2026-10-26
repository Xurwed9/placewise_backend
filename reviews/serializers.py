
from rest_framework import serializers

from .models import Review, ReviewLike, ReviewReport, ReviewPhoto
from drf_spectacular.utils import extend_schema_field




class ReviewPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewPhoto
        fields = [
            "id",
            "image",
            "thumbnail",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "thumbnail",
            "created_at",
        ]


class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )
    user_id = serializers.IntegerField(read_only=True)
    likes_count = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    reject_reason = serializers.SerializerMethodField()
    photos = serializers.SerializerMethodField()
    photo_objects = ReviewPhotoSerializer(
        source="photos",
        many=True,
        read_only=True,
    )
    photo_urls = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
        "id",
        "user_id",
        "user_name",
        "place",
        "rating",
        "text",
        "lang",
        "status",
        "reject_reason",
        "photos",
        "photo_objects",
        "photo_urls",
        "owner_reply",
        "owner_reply_at",
        "created_at",
        "likes",
        "likes_count",
        "is_liked",
    ]
        read_only_fields = fields

    @extend_schema_field(serializers.IntegerField())
    def get_likes_count(self, obj) -> int:
        return obj.likes.count()

    @extend_schema_field(serializers.IntegerField())
    def get_likes(self, obj) -> int:
        return obj.likes.count()

    @extend_schema_field(serializers.CharField())
    def get_status(self, obj) -> str:
        if obj.status == Review.Status.APPROVED:
            return "published"
        return obj.status

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_reject_reason(self, obj) -> str:
        if obj.status == Review.Status.REJECTED:
            return obj.moderation_note
        return ""

    @extend_schema_field(serializers.ListField(
        child=serializers.URLField(),
    ))
    def get_photos(self, obj) -> list[str]:
        return self.get_photo_urls(obj)

    @extend_schema_field(serializers.ListField(
        child=serializers.URLField(),
    ))
    def get_photo_urls(self, obj) -> list[str]:
        request = self.context.get("request")
        urls = []

        for photo in obj.photos.all():
            if not photo.image:
                continue

            try:
                url = photo.image.url
            except ValueError:
                continue

            urls.append(
                request.build_absolute_uri(url)
                if request is not None
                else url
            )

        return urls

    @extend_schema_field(serializers.BooleanField())
    def get_is_liked(self, obj) -> bool:
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.likes.filter(user=request.user).exists()


class ReviewCreateSerializer(serializers.ModelSerializer):
    photos = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
        max_length=5,
    )

    class Meta:
        model = Review
        fields = ["rating", "text", "lang", "photos"]
        extra_kwargs = {
            "lang": {"required": False},
        }

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError(
                "Оценка должна быть от 1 до 5.",
                code="REVIEW_RATING_INVALID",
            )
        return value

    def validate_lang(self, value):
        if value not in {"ru", "tg", "en"}:
            raise serializers.ValidationError(
                "Забон бояд ru, tg ё en бошад.",
                code="REVIEW_LANG_INVALID",
            )
        return value

    def validate_text(self, value):
        value = value.strip()

        if len(value) < 50:
            raise serializers.ValidationError(
                "Отзыв должен содержать минимум 50 символов.",
                code="REVIEW_TOO_SHORT",
            )

        if len(value) > 2000:
            raise serializers.ValidationError(
                "Отзыв не должен превышать 2000 символов.",
                code="REVIEW_TOO_LONG",
            )

        return value



class ReviewUpdateSerializer(serializers.ModelSerializer):
    photos = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
        max_length=5,
    )
    remove_photo_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Review
        fields = ["rating", "text", "lang", "photos", "remove_photo_ids"]
        extra_kwargs = {
            "lang": {"required": False},
        }

    def validate_lang(self, value):
        if value not in {"ru", "tg", "en"}:
            raise serializers.ValidationError(
                "Забон бояд ru, tg ё en бошад."
            )
        return value

    def validate_text(self, value):
        value = value.strip()

        if len(value) < 50:
            raise serializers.ValidationError(
                "Отзыв должен содержать минимум 50 символов."
            )

        if len(value) > 2000:
            raise serializers.ValidationError(
                "Отзыв не должен превышать 2000 символов."
            )

        return value



class ReviewReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewReport
        fields = ["reason"]

    def validate_reason(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Сабаби шикоятро нависед."
            )

        return value



class ModerateReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject"]
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )
