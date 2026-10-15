
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class Review(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Дар интизори санҷиш"
        APPROVED = "approved", "Нашр шудааст"
        REJECTED = "rejected", "Рад шудааст"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    place = models.ForeignKey(
        "places.Place",
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    rating = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ]
    )

    text = models.TextField(max_length=2000)
    lang = models.CharField(
        max_length=2,
        choices=[
            ("ru", "Русский"),
            ("tg", "Тоҷикӣ"),
            ("en", "English"),
        ],
        default="ru",
        verbose_name="Забони отзыв",
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_reviews",
    )

    moderation_note = models.CharField(
        max_length=500,
        blank=True,
    )

    owner_reply = models.TextField(
        max_length=2000,
        blank=True,
        default="",
    )
    owner_reply_at = models.DateTimeField(
        null=True,
        blank=True,
    )


    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["place", "status", "-created_at"],
                name="review_place_status_date_idx",
            ),
        ]

    def __str__(self):
        return f"Review #{self.pk} — {self.rating}/5"





def update_place_rating(place):
    approved_reviews = Review.objects.filter(
        place=place,
        status=Review.Status.APPROVED,
    )

    stats = approved_reviews.aggregate(
        average_rating=Avg("rating"),
        total_reviews=Count("id"),
    )

    place.rating = round(stats["average_rating"] or 0, 1)
    place.reviews_count = stats["total_reviews"]

    place.save(
        update_fields=["rating", "reviews_count"]
    )


class ReviewLike(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_likes",
    )
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "review"],
                name="unique_review_like",
            ),
        ]

    def __str__(self):
        return f"User {self.user_id} likes review {self.review_id}"


class ReviewReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Дар интизори санҷиш"
        RESOLVED = "resolved", "Баррасӣ шудааст"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_reports",
    )
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reason = models.CharField(max_length=500)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "review"],
                name="unique_review_report",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Report #{self.pk} for review {self.review_id}"



class ReviewPhoto(models.Model):
    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="reviews/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Photo for review {self.review_id}"



@receiver(post_save, sender=Review)
def review_saved(sender, instance, **kwargs):
    update_place_rating(instance.place)


@receiver(post_delete, sender=Review)
def review_deleted(sender, instance, **kwargs):
    update_place_rating(instance.place)



REVIEW_STATUS_CHOICES = Review.Status.choices
REVIEW_REPORT_STATUS_CHOICES = ReviewReport.Status.choices
