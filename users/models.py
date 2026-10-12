
from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    phone = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Телефон",
    )

    name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="Имя",
    )

    avatar = models.ImageField(
        upload_to="avatars/",
        blank=True,
        null=True,
        verbose_name="Аватар",
    )

    language = models.CharField(
        max_length=2,
        choices=[
            ("ru", "Русский"),
            ("tg", "Таджикский"),
            ("en", "English"),
        ],
        default="ru",
        verbose_name="Язык",
    )

    is_blocked = models.BooleanField(
        default=False,
        verbose_name="Заблокирован",
    )

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.phone




class PhoneOTP(models.Model):
    phone = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["phone", "created_at"],
                name="otp_phone_created_idx",
            ),
        ]
        verbose_name = "SMS-код"
        verbose_name_plural = "SMS-кодҳо"

    def __str__(self):
        return f"OTP for {self.phone}"
