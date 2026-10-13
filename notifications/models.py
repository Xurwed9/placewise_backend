
from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        REVIEW_APPROVED = "review_approved", "Отзыв нашр шуд"
        REVIEW_REJECTED = "review_rejected", "Отзыв рад шуд"
        OWNER_REPLY = "owner_reply", "Ҷавоби соҳиби ҷой"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=Type.choices,
    )

    title = models.CharField(max_length=200)
    message = models.TextField(max_length=1000)

    review = models.ForeignKey(
        "reviews.Review",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    is_read = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "is_read", "-created_at"],
                name="notification_user_read_idx",
            ),
        ]

    def __str__(self):
        return f"Notification #{self.pk} for user {self.user_id}"
