
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from places.models import Category, Place
from reviews.models import Review


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
            {"rating": 5, "text": "Отличное место"},
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
            {"rating": 5, "text": "Хорошее место"},
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

