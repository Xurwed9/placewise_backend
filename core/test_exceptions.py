from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from places.models import Category, Place


class APIErrorEnvelopeTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_not_found_has_error_envelope(self):
        response = self.client.get("/api/v1/places/missing-place/")
        self.assertEqual(response.status_code, 404)

        error = response.json()["error"]
        self.assertEqual(error["code"], "NOT_FOUND")
        self.assertTrue(error["message"])
        self.assertIn("detail", response.json())

    def test_not_found_message_uses_request_language(self):
        response = self.client.get(
            "/api/v1/places/missing-place/?lang=en"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["message"],
            "Not found.",
        )

    def test_auth_required_has_error_envelope(self):
        response = self.client.get("/api/v1/me/favorites/")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"]["code"],
            "AUTH_REQUIRED",
        )

    def test_method_not_allowed_has_error_envelope(self):
        response = self.client.post("/api/v1/places/map/")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            response.json()["error"]["code"],
            "METHOD_NOT_ALLOWED",
        )

    def test_manual_error_has_error_envelope_and_legacy_detail(self):
        response = self.client.get("/api/v1/places/?sort=unknown")
        self.assertEqual(response.status_code, 400)
        data = response.json()

        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("sort", data["error"]["message"])
        self.assertEqual(data["detail"], data["error"]["message"])

    def test_manual_detail_error_has_error_envelope(self):
        response = self.client.get("/api/v1/places/?lat=38.5")
        self.assertEqual(response.status_code, 400)
        data = response.json()

        self.assertEqual(data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("lat", data["error"]["message"])
        self.assertIn("detail", data)

    def test_validation_error_has_error_envelope(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="+992900000301",
            phone="+992900000301",
        )
        category = Category.objects.create(
            key="error-envelope",
            slug="error-envelope",
            name={"ru": "Кафе"},
        )
        place = Place.objects.create(
            category=category,
            name={"ru": "Кафе"},
            slug="error-envelope-place",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            f"/api/v1/places/{place.slug}/claim/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["error"]["code"],
            "VALIDATION_ERROR",
        )
        self.assertIn("details", response.json()["error"])
