from rest_framework import serializers
from .models import User
from core.image_processing import process_uploaded_image


class UserProfileSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(read_only=True)
    lang = serializers.CharField(source="language", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "name",
            "language",
            "lang",
            "avatar",
            "role",
        ]
        read_only_fields = fields


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    avatar = serializers.ImageField(required=False)
    language = serializers.ChoiceField(
        choices=["ru", "tg", "en"],
        required=False,
    )
    lang = serializers.ChoiceField(
        choices=["ru", "tg", "en"],
        source="language",
        required=False,
    )

    class Meta:
        model = User
        fields = ["name", "language", "lang", "avatar"]

    def validate_language(self, value):
        if value not in {"ru", "tg", "en"}:
            raise serializers.ValidationError(
                "Забон бояд ru, tg ё en бошад."
            )
        return value

    def validate_avatar(self, value):
        try:
            return process_uploaded_image(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

class ModerateReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject"]
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )



class AdminUserSerializer(serializers.ModelSerializer):
    lang = serializers.CharField(source="language", read_only=True)
    language = serializers.ChoiceField(
        choices=["ru", "tg", "en"],
        required=False,
    )
    role = serializers.ChoiceField(
        choices=[
            ("user", "Корбари оддӣ"),
            ("owner", "Соҳиби ҷой"),
            ("moderator", "Модератор"),
            ("admin", "Админ"),
        ],
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "name",
            "language",
            "lang",
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

    def update(self, instance, validated_data):
        role = validated_data.get("role")
        instance = super().update(instance, validated_data)

        if role is not None:
            instance.is_staff = role in {"moderator", "admin"}
            instance.save(update_fields=["is_staff"])

        return instance
