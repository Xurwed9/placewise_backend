from rest_framework import serializers
from .models import User


class UserProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = ["id", "phone", "name", "language", "avatar"]
        read_only_fields = ["id", "phone"]

    def validate_language(self, value):
        if value not in {"ru", "tg", "en"}:
            raise serializers.ValidationError(
                "Забон бояд ru, tg ё en бошад."
            )
        return value


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = ["name", "language", "avatar"]





class ModerateReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject"]
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )
