from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from places.models import Brand, Category, Favorite, Place, PlacePhoto


class PlaceDetailTZTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        User = get_user_model()

        self.user = User.objects.create_user(
            username="detail_favorite_user",
            phone="+992900000101",
        )
        self.other_user = User.objects.create_user(
            username="detail_other_user",
            phone="+992900000102",
        )

        self.category = Category.objects.create(
            key="detail-tz",
            slug="detail-tz",
            name={"ru": "Рестораны", "tg": "Тарабхонаҳо", "en": "Restaurants"},
        )
        self.brand = Brand.objects.create(
            name={"ru": "Lavash"},
            slug="lavash-detail-tz",
            branches_count=12,
        )
        self.place = Place.objects.create(
            category=self.category,
            brand=self.brand,
            name={"ru": "Lavash", "tg": "Lavash", "en": "Lavash"},
            slug="lavash-detail-tz",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
            opening_hours={
                day: ["08:00", "22:00"]
                for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            },
        )
        self.photo = PlacePhoto.objects.create(
            place=self.place,
            image="places/detail-tz.jpg",
            credit="2GIS",
            alt={"ru": "Фото", "tg": "Акс", "en": "Photo"},
        )
        self.url = f"/api/v1/places/{self.place.slug}/"

    def test_detail_contains_spec_fields(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["hours_text"], "ежедневно 08:00–22:00")
        self.assertIn(data["open_now"], (True, False))
        self.assertFalse(data["is_favorite"])
        self.assertEqual(data["brand"]["branches"], 12)
        self.assertEqual(data["brand"]["branches_count"], 12)
        self.assertEqual(data["photos"][0]["credit"], "2GIS")
        self.assertIn(
            "/media/places/detail-tz.jpg",
            data["photos"][0]["url"],
        )

    def test_favorite_is_per_user_and_not_leaked_from_cache(self):
        Favorite.objects.create(user=self.user, place=self.place)

        self.client.force_authenticate(user=self.user)
        first = self.client.get(self.url)
        self.assertTrue(first.json()["is_favorite"])

        self.client.force_authenticate(user=self.other_user)
        second = self.client.get(self.url)
        self.assertFalse(second.json()["is_favorite"])

        self.client.force_authenticate(user=None)
        third = self.client.get(self.url)
        self.assertFalse(third.json()["is_favorite"])

    def test_anonymous_response_is_cached_without_favorite(self):
        self.client.force_authenticate(user=None)
        first = self.client.get(self.url)
        self.assertFalse(first.json()["is_favorite"])

        Favorite.objects.create(user=self.user, place=self.place)
        self.client.force_authenticate(user=self.user)
        second = self.client.get(self.url)

        self.assertTrue(second.json()["is_favorite"])
