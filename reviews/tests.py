from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from reviews.models import Review, ReviewPhoto, ReviewReport
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from places.models import Category, Place
from notifications.models import Notification

User = get_user_model()


class PlaceReviewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
    username="review_test_user",
    phone="+992900000001",
    name="Test User",
)

        cls.category = Category.objects.create(
            name={"ru": "Кафе"},
            slug="test-cafe-category",
        )

        cls.place = Place.objects.create(
            category=cls.category,
            name={"ru": "Тестовое кафе"},
            slug="test-cafe-reviews",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
        )

    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/v1/places/{self.place.slug}/reviews/"

    def test_guest_cannot_create_review(self):
        response = self.client.post(
            self.url,
            {"rating": 5, "text": "Хорошее место"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Review.objects.count(), 0)

    def test_authenticated_user_can_submit_review(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"rating": 5, "text": (
            "Ин ҷой хеле хуб аст, хизматрасонӣ босифат мебошад "
            "ва кормандон бо мизоҷон муносибати хуб доранд."
            ),},
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        review = Review.objects.get(place=self.place)

        self.assertEqual(review.user, self.user)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.status, Review.Status.PENDING)

    def test_rating_out_of_range_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"rating": 6, "text": "Хорошее место"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_empty_review_text_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"rating": 5, "text": "   "},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_short_review_returns_tz_error_code(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"rating": 5, "text": "Коротко"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.data["error"]["code"],
            "REVIEW_TOO_SHORT",
        )
        self.assertIn("50", response.data["error"]["message"])

    def test_pending_review_does_not_change_place_rating(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"rating": 5, "text": (
            "Ин ҷой хеле хуб аст, хизматрасонӣ босифат мебошад "
            "ва кормандон бо мизоҷон муносибати хуб доранд."
            ),},
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        self.place.refresh_from_db()

        self.assertEqual(float(self.place.rating), 0.0)
        self.assertEqual(self.place.reviews_count, 0)

    def test_only_approved_reviews_are_visible(self):
        Review.objects.create(
            user=self.user,
            place=self.place,
            rating=5,
            text="Пока не опубликован",
            status=Review.Status.PENDING,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total"], 0)




    def test_approved_review_updates_place_rating(self):
        review = Review.objects.create(
            user=self.user,
            place=self.place,
            rating=4,
            text="Хуб буд",
            status=Review.Status.APPROVED,
        )

        self.place.refresh_from_db()

        self.assertEqual(float(self.place.rating), 4.0)
        self.assertEqual(self.place.reviews_count, 1)

    def test_rejected_review_does_not_count(self):
        Review.objects.create(
            user=self.user,
            place=self.place,
            rating=2,
            text="Нашр нашавад",
            status=Review.Status.REJECTED,
        )

        self.place.refresh_from_db()

        self.assertEqual(float(self.place.rating), 0.0)
        self.assertEqual(self.place.reviews_count, 0)




    def test_review_with_links_is_rejected_automatically(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {
                "rating": 5,
                "text": (
                    "Хорошее место, но подробности смотрите тут "
                    "https://spam.example/promo и пишите нам."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        review = Review.objects.get(place=self.place)
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertEqual(review.moderation_note, "LINKS_NOT_ALLOWED")
        self.assertEqual(response.data["review"]["status"], "rejected")
        self.assertTrue(
            Notification.objects.filter(
                review=review,
                notification_type=Notification.Type.REVIEW_REJECTED,
            ).exists()
        )

    def test_review_with_phone_is_rejected_automatically(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {
                "rating": 5,
                "text": (
                    "Отличное место, всё понравилось. Звоните нам "
                    "по номеру +992 900 123 456 для подробностей."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        review = Review.objects.get(place=self.place)
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertEqual(review.moderation_note, "PHONE_NOT_ALLOWED")

    def test_review_with_profanity_is_rejected_automatically(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {
                "rating": 1,
                "text": (
                    "Это место полный аблаҳ, обслуживание ужасное "
                    "и персонал совсем не помогает клиентам."
                ),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        review = Review.objects.get(place=self.place)
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertEqual(review.moderation_note, "PROFANITY")


class ReviewNotificationIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = User.objects.create_user(
            username="integration_reviewer",
            phone="+992900000021",
            name="Review Author",
            language="tg",
        )

        cls.moderator = User.objects.create_user(
            username="integration_moderator",
            phone="+992900000022",
            name="Moderator",
            role="moderator",
            is_staff=True,
        )

        cls.owner = User.objects.create_user(
            username="integration_owner",
            phone="+992900000023",
            name="Place Owner",
            role="owner",
        )

        cls.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="integration-notification-category",
        )

        cls.place = Place.objects.create(
            category=cls.category,
            name={"ru": "Тестовое кафе"},
            slug="integration-notification-place",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
            owner=cls.owner,
        )

    def setUp(self):
        self.client = APIClient()

    def create_review(self, status_value=Review.Status.PENDING):
        return Review.objects.create(
            user=self.reviewer,
            place=self.place,
            rating=5,
            text=(
                "Ин ҷой хеле хуб аст ва хизматрасонӣ босифат мебошад. "
                "Кормандон бо мизоҷон муносибати хуб доранд."
            ),
            status=status_value,
        )

    def test_approval_creates_notification(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/approve"
        )

        self.assertEqual(response.status_code, 200)

        notification = Notification.objects.get(
            user=self.reviewer,
            review=review,
        )
        self.assertEqual(
            notification.notification_type,
            Notification.Type.REVIEW_APPROVED,
        )
        self.assertEqual(notification.title, "Отзыв нашр шуд")

    def test_rejection_creates_notification_with_reason(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/reject",
            {"reason": "Маълумоти нокифоя"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        notification = Notification.objects.get(
            user=self.reviewer,
            review=review,
        )
        self.assertEqual(
            notification.notification_type,
            Notification.Type.REVIEW_REJECTED,
        )
        self.assertIn("Маълумоти нокифоя", notification.message)

    def test_owner_reply_creates_notification(self):
        review = self.create_review(Review.Status.APPROVED)
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            f"/api/v1/owner/reviews/{review.id}/reply/",
            {"reply": "Ташаккур барои фикри шумо!"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        notification = Notification.objects.get(
            user=self.reviewer,
            review=review,
        )
        self.assertEqual(
            notification.notification_type,
            Notification.Type.OWNER_REPLY,
        )
        self.assertEqual(notification.title, "Ҷавоби соҳиби ҷой")

    def test_unrelated_user_cannot_reply_to_review(self):
        stranger = User.objects.create_user(
            username="integration_stranger",
            phone="+992900000024",
            name="Stranger",
        )
        review = self.create_review(Review.Status.APPROVED)
        self.client.force_authenticate(user=stranger)

        response = self.client.post(
            f"/api/v1/owner/reviews/{review.id}/reply/",
            {"reply": "Ҷавоб"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Notification.objects.filter(
                user=self.reviewer,
                review=review,
                notification_type=Notification.Type.OWNER_REPLY,
            ).exists()
        )



class ReviewPhotoUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.user = User.objects.create_user(
            username="photo_test_user",
            phone="+992900000021",
            name="Photo Test User",
        )

        cls.other_user = User.objects.create_user(
            username="other_photo_user",
            phone="+992900000022",
            name="Other Photo User",
        )

        cls.category = Category.objects.create(
            name={"ru": "Кафе"},
            slug="photo-test-category",
        )

        cls.place = Place.objects.create(
            category=cls.category,
            name={"ru": "Тестовое кафе"},
            slug="photo-test-place",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
        )

    def setUp(self):
        self.client = APIClient()

        self.review = Review.objects.create(
            user=self.user,
            place=self.place,
            rating=5,
            text=(
                "Ин ҷой хеле хуб аст ва хизматрасонӣ "
                "босифат мебошад."
            ),
            status=Review.Status.PENDING,
        )

        self.url = (
            f"/api/v1/reviews/{self.review.id}/photos"
        )

    def make_image(self):
        buffer = BytesIO()

        image = Image.new("RGB", (100, 80), color="red")
        image.save(buffer, format="JPEG")

        return SimpleUploadedFile(
            "test.jpg",
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    def test_guest_cannot_upload_photo(self):
        response = self.client.post(
            self.url,
            {"image": self.make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 401)

    def test_owner_can_upload_photo(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"image": self.make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("image", response.json())

        photo = ReviewPhoto.objects.get(review=self.review)

        with Image.open(photo.image) as saved_image:
            self.assertEqual(saved_image.format, "WEBP")

    def test_other_user_cannot_upload_photo(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(
            self.url,
            {"image": self.make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(ReviewPhoto.objects.count(), 0)

    def test_invalid_file_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        invalid_file = SimpleUploadedFile(
            "bad.jpg",
            b"this is not a real image",
            content_type="image/jpeg",
        )

        response = self.client.post(
            self.url,
            {"image": invalid_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ReviewPhoto.objects.count(), 0)

    def test_sixth_photo_is_rejected(self):
    # Барои отзыв аллакай 5 акс месозем.
        for _ in range(5):
            ReviewPhoto.objects.create(
                review=self.review,
                image=SimpleUploadedFile(
                    f"photo_{_}.jpg",
                    b"test-image",
                    content_type="image/jpeg",
                ),
            )

        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {"image": self.make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ReviewPhoto.objects.filter(review=self.review).count(),
            5,
        )



    def make_stored_photo(self):
        return ReviewPhoto.objects.create(
            review=self.review,
            image=SimpleUploadedFile(
                "stored-photo.jpg",
                b"test-image",
                content_type="image/jpeg",
            ),
            thumbnail=SimpleUploadedFile(
                "stored-photo-thumb.jpg",
                b"test-thumbnail",
                content_type="image/jpeg",
            ),
        )

    def test_owner_can_delete_photo_by_endpoint(self):
        photo = self.make_stored_photo()
        image_path = Path(photo.image.path)
        thumbnail_path = Path(photo.thumbnail.path)
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(
            f"{self.url}/{photo.id}"
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ReviewPhoto.objects.filter(id=photo.id).exists())
        self.assertFalse(Path(image_path).exists())
        self.assertFalse(Path(thumbnail_path).exists())

    def test_other_user_cannot_delete_photo(self):
        photo = self.make_stored_photo()
        self.client.force_authenticate(user=self.other_user)

        response = self.client.delete(
            f"{self.url}/{photo.id}"
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(ReviewPhoto.objects.filter(id=photo.id).exists())

    def test_patch_remove_photo_ids_deletes_files(self):
        photo = self.make_stored_photo()
        image_path = Path(photo.image.path)
        thumbnail_path = Path(photo.thumbnail.path)
        self.client.force_authenticate(user=self.user)

        response = self.client.patch(
            f"/api/v1/reviews/{self.review.id}",
            {"remove_photo_ids": [photo.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(ReviewPhoto.objects.filter(id=photo.id).exists())
        self.assertFalse(Path(image_path).exists())
        self.assertFalse(Path(thumbnail_path).exists())

    def test_deleting_review_deletes_photo_files(self):
        photo = self.make_stored_photo()
        image_path = Path(photo.image.path)
        thumbnail_path = Path(photo.thumbnail.path)
        self.client.force_authenticate(user=self.user)

        response = self.client.delete(
            f"/api/v1/reviews/{self.review.id}"
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Path(image_path).exists())
        self.assertFalse(Path(thumbnail_path).exists())


class ReviewModerationAndReportAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.reviewer = User.objects.create_user(
            username="moderation_reviewer",
            phone="+992900000071",
            name="Review Author",
            language="tg",
        )

        cls.moderator = User.objects.create_user(
            username="moderation_moderator",
            phone="+992900000072",
            name="Moderator",
            role="moderator",
            is_staff=True,
        )

        cls.regular_user = User.objects.create_user(
            username="moderation_regular",
            phone="+992900000073",
            name="Regular User",
        )

        cls.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="moderation-test-category",
        )

        cls.place = Place.objects.create(
            category=cls.category,
            name={"ru": "Тестовое кафе"},
            slug="moderation-test-place",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
        )

    def setUp(self):
        self.client = APIClient()

    def create_review(
        self,
        status_value=Review.Status.PENDING,
        user=None,
        place=None,
    ):
        return Review.objects.create(
            user=user or self.reviewer,
            place=place or self.place,
            rating=5,
            text=(
                "Ин ҷой хеле хуб аст ва хизматрасонӣ босифат мебошад. "
                "Кормандон бо мизоҷон муносибати хуб доранд."
            ),
            status=status_value,
        )

    def test_guest_cannot_access_moderation_queue(self):
        response = self.client.get("/api/v1/admin/reviews/")
        self.assertEqual(response.status_code, 401)

    def test_regular_user_cannot_access_moderation_queue(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/v1/admin/reviews/")

        self.assertEqual(response.status_code, 403)

    def test_moderator_queue_contains_only_pending_reviews(self):
        pending_review = self.create_review()
        self.create_review(
            Review.Status.APPROVED,
            user=self.regular_user,
        )

        self.client.force_authenticate(user=self.moderator)

        response = self.client.get("/api/v1/admin/reviews/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            pending_review.id,
        )

    def test_regular_user_cannot_moderate_review(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/approve"
        )

        self.assertEqual(response.status_code, 403)

        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PENDING)

    def test_reject_requires_reason(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/reject"
        )

        self.assertEqual(response.status_code, 400)

        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.PENDING)

    def test_moderator_cannot_moderate_same_review_twice(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.moderator)

        first_response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/approve"
        )
        second_response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/reject",
            {"reason": "Сабаб"},
            format="json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 404)

        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.APPROVED)

    def test_admin_review_queue_alias_accepts_status_filter(self):
        pending_review = self.create_review()
        approved_review = self.create_review(
            Review.Status.APPROVED,
            user=self.regular_user,
        )
        self.client.force_authenticate(user=self.moderator)

        response = self.client.get(
            "/api/v1/admin/reviews?status=pending"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["items"][0]["id"], pending_review.id)

        approved_only = self.client.get(
            "/api/v1/admin/reviews?status=approved"
        )
        self.assertEqual(approved_only.status_code, 200)
        self.assertEqual(approved_only.data["total"], 1)
        self.assertEqual(
            approved_only.data["items"][0]["id"],
            approved_review.id,
        )

        published_only = self.client.get(
            "/api/v1/admin/reviews?status=published"
        )
        self.assertEqual(published_only.status_code, 200)
        self.assertEqual(published_only.data["total"], 1)
        self.assertEqual(
            published_only.data["items"][0]["id"],
            approved_review.id,
        )

    def test_admin_can_approve_review_via_tz_alias(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/approve"
        )

        self.assertEqual(response.status_code, 200, response.data)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.APPROVED)

    def test_admin_can_reject_review_via_tz_alias(self):
        review = self.create_review()
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            f"/api/v1/admin/reviews/{review.id}/reject",
            {"reason": "Нодуруст"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        review.refresh_from_db()
        self.assertEqual(review.status, Review.Status.REJECTED)
        self.assertEqual(review.moderation_note, "Нодуруст")

    def test_moderation_reports_support_page_limit_pagination(self):
        review = self.create_review(Review.Status.APPROVED)
        ReviewReport.objects.create(
            user=self.regular_user,
            review=review,
            reason="Первая жалоба",
        )
        ReviewReport.objects.create(
            user=self.moderator,
            review=review,
            reason="Вторая жалоба",
        )
        self.client.force_authenticate(user=self.moderator)

        response = self.client.get(
            "/api/v1/admin/reports?page=1&limit=1"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["page"], 1)
        self.assertEqual(response.data["limit"], 1)
        self.assertEqual(len(response.data["items"]), 1)

    def test_regular_user_cannot_list_reports(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/v1/admin/reports")

        self.assertEqual(response.status_code, 403)

    def test_moderator_can_list_reports(self):
        review = self.create_review(Review.Status.APPROVED)
        ReviewReport.objects.create(
            user=self.regular_user,
            review=review,
            reason="Маълумоти нодуруст",
        )

        self.client.force_authenticate(user=self.moderator)

        response = self.client.get("/api/v1/admin/reports")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["reason"], "Маълумоти нодуруст")

    def test_moderator_can_filter_pending_reports(self):
        review = self.create_review(Review.Status.APPROVED)

        ReviewReport.objects.create(
            user=self.regular_user,
            review=review,
            reason="Шикояти нав",
        )

        resolved_report = ReviewReport.objects.create(
            user=self.reviewer,
            review=review,
            reason="Шикояти ҳалшуда",
            status=ReviewReport.Status.RESOLVED,
        )

        self.client.force_authenticate(user=self.moderator)

        response = self.client.get(
            "/api/v1/admin/reports?status=pending"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "pending")
        self.assertNotEqual(response.data[0]["id"], resolved_report.id)

    def test_regular_user_cannot_resolve_report(self):
        review = self.create_review(Review.Status.APPROVED)
        report = ReviewReport.objects.create(
            user=self.reviewer,
            review=review,
            reason="Санҷиш",
        )

        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            f"/api/v1/admin/reports/{report.id}/resolve"
        )

        self.assertEqual(response.status_code, 403)

        report.refresh_from_db()
        self.assertEqual(report.status, ReviewReport.Status.PENDING)

    def test_moderator_can_resolve_report(self):
        review = self.create_review(Review.Status.APPROVED)
        report = ReviewReport.objects.create(
            user=self.reviewer,
            review=review,
            reason="Санҷиш",
        )

        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            f"/api/v1/admin/reports/{report.id}/resolve"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "resolved")

        report.refresh_from_db()
        self.assertEqual(report.status, ReviewReport.Status.RESOLVED)

    def test_resolving_unknown_report_returns_404(self):
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            "/api/v1/admin/reports/999999/resolve"
        )

        self.assertEqual(response.status_code, 404)


class ReviewCreateWithPhotosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.user = User.objects.create_user(
            username="create_photos_user",
            phone="+992900000031",
            name="Create Photos User",
        )

        cls.category = Category.objects.create(
            name={"ru": "Кафе"},
            slug="create-photos-category",
        )

        cls.place = Place.objects.create(
            category=cls.category,
            name={"ru": "Кафе с фото"},
            slug="create-photos-place",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
        )

    def setUp(self):
        self.client = APIClient()

    def make_image(self, name="photo.jpg"):
        buffer = BytesIO()

        image = Image.new("RGB", (100, 80), color="blue")
        image.save(buffer, format="JPEG")

        return SimpleUploadedFile(
            name,
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    def test_review_can_be_created_with_photos(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            f"/api/v1/places/{self.place.slug}/reviews/",
            {
                "rating": 5,
                "text": (
                    "Ин ҷой хеле хуб аст, хизматрасонӣ босифат "
                    "мебошад ва кормандон хушмуомила ҳастанд."
                ),
                "photos": [
                    self.make_image("one.jpg"),
                    self.make_image("two.jpg"),
                ],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)

        review = Review.objects.get(place=self.place, user=self.user)

        self.assertEqual(review.photos.count(), 2)
        self.assertEqual(len(response.data["review"]["photos"]), 2)

        for photo in review.photos.all():
            with Image.open(photo.image) as saved_image:
                self.assertEqual(saved_image.format, "WEBP")

    def test_review_photos_are_limited_to_five(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            f"/api/v1/places/{self.place.slug}/reviews/",
            {
                "rating": 5,
                "text": (
                    "Ин ҷой хеле хуб аст, хизматрасонӣ босифат "
                    "мебошад ва кормандон хушмуомила ҳастанд."
                ),
                "photos": [
                    self.make_image(f"photo-{index}.jpg")
                    for index in range(6)
                ],
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Review.objects.filter(place=self.place, user=self.user).exists()
        )
