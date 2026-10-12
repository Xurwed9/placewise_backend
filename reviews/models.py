
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




@receiver(post_save, sender=Review)
def review_saved(sender, instance, **kwargs):
    update_place_rating(instance.place)


@receiver(post_delete, sender=Review)
def review_deleted(sender, instance, **kwargs):
    update_place_rating(instance.place)

