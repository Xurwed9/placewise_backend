
from rest_framework import serializers

from .models import Review, ReviewLike, ReviewReport, ReviewPhoto




class ReviewPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewPhoto
        fields = ["id", "image", "created_at"]
        read_only_fields = ["id", "created_at"]



class ReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(
        source="user.name",
        read_only=True,
    )
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    photos = ReviewPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Review
        fields = [
        "id",
        "user_name",
        "place",
        "rating",
        "text",
        "lang",
        "photos",
        "owner_reply",
        "owner_reply_at",
        "created_at",
        "likes_count",
        "is_liked",
    ]
        read_only_fields = fields

    def get_likes_count(self, obj):
        return obj.likes.count()

    def get_is_liked(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.likes.filter(user=request.user).exists()


class ReviewCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["rating", "text", "lang"]
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



class ReviewUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Review
        fields = ["rating", "text"]

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
