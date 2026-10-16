
from django.conf import settings
from django.contrib.gis.db import models
from django.db.models import Q



class Category(models.Model):
    name = models.JSONField(default=dict)
    slug = models.SlugField(max_length=150, unique=True)

    key = models.SlugField(
    max_length=150,
    unique=True,
    )
    image = models.ImageField(
        upload_to="categories/",
        blank=True,
    )

    icon = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Категория"
        verbose_name_plural = "Категории"

    def __str__(self):
        return self.slug




class Brand(models.Model):
    name = models.JSONField(default=dict)
    slug = models.SlugField(max_length=200, unique=True)
    branches_count = models.PositiveIntegerField(default=1)

    logo = models.ImageField(
        upload_to="brands/",
        blank=True,
    )
    website = models.URLField(
        max_length=500,
        blank=True,
    )
    instagram = models.URLField(
        max_length=500,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Бренд"
        verbose_name_plural = "Бренды"

    def __str__(self):
        return self.slug



class Place(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PUBLISHED = "published", "Опубликовано"
        HIDDEN = "hidden", "Скрыто"

    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="places",
    )

    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="places",
    )

    name = models.JSONField(default=dict)
    slug = models.SlugField(max_length=250, unique=True)
    about = models.JSONField(default=dict, blank=True)
    subcategory = models.JSONField(default=dict, blank=True)

    address = models.JSONField(default=dict)
    district = models.CharField(max_length=150, blank=True)

    location = models.PointField(
        geography=True,
        srid=4326,
        null=True,
        blank=True,
    )

    phones = models.JSONField(default=list, blank=True)
    website = models.URLField(max_length=500, blank=True)
    opening_hours = models.JSONField(default=dict, blank=True)

    price_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
    )
    reviews_count = models.PositiveIntegerField(default=0)

    ext_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        null=True,
        blank=True,
    )
    ext_reviews = models.PositiveIntegerField(default=0)

    source = models.CharField(max_length=50, blank=True)
    source_id = models.CharField(max_length=200, blank=True)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_places",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "category"]),
            models.Index(fields=["district"]),
            models.Index(fields=["rating"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(price_level__isnull=True)
                | Q(price_level__gte=1, price_level__lte=4),
                name="place_price_level_1_4",
            ),
            models.UniqueConstraint(
                fields=["source", "source_id"],
                condition=~Q(source_id=""),
                name="unique_place_source_id",
            ),
        ]
        verbose_name = "Место"
        verbose_name_plural = "Места"

    def __str__(self):
        return self.slug


class PlacePhoto(models.Model):
    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(upload_to="places/%Y/%m/")
    thumbnail = models.ImageField(
        upload_to="places/thumbnails/%Y/%m/",
        blank=True,
    )
    alt = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_cover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "Фото места"
        verbose_name_plural = "Фото мест"

    def __str__(self):
        return f"Photo for {self.place.slug}"




class Favorite(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "place"],
                name="unique_user_favorite_place",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.place}"




class Claim(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Дар интизорӣ"
        APPROVED = "approved", "Тасдиқ шуд"
        REJECTED = "rejected", "Рад шуд"

    place = models.ForeignKey(
        Place,
        on_delete=models.CASCADE,
        related_name="claims",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="place_claims",
    )
    document_url = models.URLField(max_length=1000)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["place", "user"],
                condition=models.Q(status="pending"),
                name="unique_pending_claim_per_user_place",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.place} ({self.status})"


class AnalyticsEvent(models.Model):
    class EventType(models.TextChoices):
        PLACE_VIEW = "place_view", "Тамошои ҷой"
        PHONE_CLICK = "phone_click", "Клик ба телефон"
        WHATSAPP_CLICK = "whatsapp_click", "Клик ба WhatsApp"
        TELEGRAM_CLICK = "telegram_click", "Клик ба Telegram"
        WEBSITE_CLICK = "website_click", "Клик ба вебсайт"

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
        db_index=True,
    )

    place = models.ForeignKey(
        Place,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="analytics_events",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="placewise_analytics_events",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["event_type", "created_at"],
                name="analytics_type_date_idx",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} — {self.created_at}"

PLACE_STATUS_CHOICES = Place.Status.choices
CLAIM_STATUS_CHOICES = Claim.Status.choices