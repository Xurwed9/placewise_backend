
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from places.models import Category, Place
from reviews.models import Review
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
        self.assertEqual(response.data, [])




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
            f"/api/v1/moderation/reviews/{review.id}/",
            {"action": "approve"},
            format="json",
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
            f"/api/v1/moderation/reviews/{review.id}/",
            {
                "action": "reject",
                "reason": "Маълумоти нокифоя",
            },
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


