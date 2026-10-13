
from django.contrib import admin

from .models import Review, ReviewLike, ReviewReport


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "place",
        "user",
        "rating",
        "status",
        "created_at",
        "moderator",
    )
    list_filter = ("status", "rating", "created_at")
    search_fields = (
        "text",
        "user__phone",
        "user__name",
        "place__slug",
    )
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 30
    actions = ("publish_reviews", "reject_reviews")

    @admin.action(description="Нашр кардани отзывҳои интихобшуда")
    def publish_reviews(self, request, queryset):
        count = 0

        for review in queryset:
            review.status = Review.Status.APPROVED
            review.moderator = request.user
            review.moderation_note = ""
            review.save(
                update_fields=[
                    "status",
                    "moderator",
                    "moderation_note",
                    "updated_at",
                ]
            )
            count += 1

        self.message_user(
            request,
            f"{count} отзыв нашр шуд.",
        )

    @admin.action(description="Рад кардани отзывҳои интихобшуда")
    def reject_reviews(self, request, queryset):
        count = 0

        for review in queryset:
            review.status = Review.Status.REJECTED
            review.moderator = request.user

            if not review.moderation_note:
                review.moderation_note = (
                    "Отзыв аз тарафи модератор рад карда шуд."
                )

            review.save(
                update_fields=[
                    "status",
                    "moderator",
                    "moderation_note",
                    "updated_at",
                ]
            )
            count += 1

        self.message_user(
            request,
            f"{count} отзыв рад карда шуд.",
        )


@admin.register(ReviewReport)
class ReviewReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "review",
        "user",
        "reason",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "reason",
        "user__phone",
        "review__text",
    )
    readonly_fields = ("created_at",)
    list_per_page = 30
    actions = ("mark_resolved",)

    @admin.action(description="Шикоятҳои интихобшударо баррасишуда нишон додан")
    def mark_resolved(self, request, queryset):
        count = queryset.update(
            status=ReviewReport.Status.RESOLVED
        )
        self.message_user(
            request,
            f"{count} шикоят баррасӣ шуд.",
        )


@admin.register(ReviewLike)
class ReviewLikeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "review", "created_at")
    search_fields = ("user__phone", "review__text")
    readonly_fields = ("created_at",)
    list_per_page = 30
