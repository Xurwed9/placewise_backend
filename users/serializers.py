from rest_framework import serializers
from .models import User


class UserProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=False)

    class Meta:
        model = User
        fields = ["id", "phone", "name", "language", "avatar", "role"]
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
        fields = ["name", "phone", "language", "avatar","role"]


class ModerateReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject"]
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )



class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "name",
            "language",
            "role",
            "is_blocked",
            "is_active",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "phone",
            "is_staff",
            "is_superuser",
            "date_joined",
            "last_login",
        ]

    def validate_role(self, value):
        allowed_roles = {
            "user",
            "owner",
            "moderator",
            "admin",
        }

        if value not in allowed_roles:
            raise serializers.ValidationError(
                "Нақш нодуруст аст."
            )

        request = self.context.get("request")

        # Танҳо superuser метавонад admin таъин кунад.
        if value == "admin" and not (
            request and request.user.is_superuser
        ):
            raise serializers.ValidationError(
                "Танҳо superuser метавонад нақши admin диҳад."
            )

        return value
