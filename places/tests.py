
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from rest_framework import status

from places.models import Category, Place, Favorite


class PlacewiseAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_categories_endpoint(self):
        response = self.client.get(
            "/api/v1/categories/?lang=tg"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    def test_places_endpoint(self):
        response = self.client.get(
            "/api/v1/places/?lang=ru"
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

    def test_places_pagination(self):
        response = self.client.get(
            "/api/v1/places/?page=1&page_size=10"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.json()["results"]),
            min(response.json()["count"], 10),
        )

    def test_invalid_min_rating(self):
        response = self.client.get(
            "/api/v1/places/?min_rating=invalid"
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_price_level(self):
        response = self.client.get(
            "/api/v1/places/?price_level=10"
        )

        self.assertEqual(response.status_code, 400)

    def test_map_requires_bbox(self):
        response = self.client.get(
            "/api/v1/places/map/"
        )

        self.assertEqual(response.status_code, 400)

    def test_map_rejects_invalid_bbox(self):
        response = self.client.get(
            "/api/v1/places/map/?bbox=invalid"
        )

        self.assertEqual(response.status_code, 400)

    def test_similar_places_returns_404_for_missing_place(self):
        response = self.client.get(
            "/api/v1/places/place-that-does-not-exist/similar/"
        )

        self.assertEqual(response.status_code, 404)




class FavoriteAPITests(TestCase):
    def setUp(self):
        User = get_user_model()

        self.user = User.objects.create_user(
            phone="+992900000001",
            username="+992900000001",
            password="TestPassword123!",
        )

        self.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="favorite-test-category",
        )

        self.place = Place.objects.create(
            category=self.category,
            name={
                "ru": "Тестовое кафе",
                "tg": "Қаҳвахонаи тестӣ",
                "en": "Test Cafe",
            },
            slug="favorite-test-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_favorites_empty(self):
        response = self.client.get("/api/v1/favorites/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_add_favorite(self):
        response = self.client.post(
            "/api/v1/favorites/",
            {"place": self.place.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Favorite.objects.filter(
                user=self.user,
                place=self.place,
            ).exists()
        )

    def test_adding_same_favorite_twice_does_not_duplicate(self):
        url = "/api/v1/favorites/"
        data = {"place": self.place.id}

        first = self.client.post(url, data, format="json")
        second = self.client.post(url, data, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            Favorite.objects.filter(
                user=self.user,
                place=self.place,
            ).count(),
            1,
        )

    def test_delete_favorite(self):
        Favorite.objects.create(user=self.user, place=self.place)

        response = self.client.delete(
            f"/api/v1/favorites/{self.place.id}/"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )
        self.assertFalse(
            Favorite.objects.filter(
                user=self.user,
                place=self.place,
            ).exists()
        )

    def test_favorites_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/favorites/")

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
