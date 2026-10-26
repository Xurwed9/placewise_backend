from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from places.models import Brand, Category, Claim, Favorite, Place, PlacePhoto
from users.models import PhoneOTP


class PublicAPIContractTZTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.category = Category.objects.create(
            key="contract-restaurants",
            slug="contract-restaurants",
            name={"ru": "Рестораны", "tg": "Тарабхонаҳо", "en": "Restaurants"},
            sort_order=7,
        )
        self.brand = Brand.objects.create(
            name={"ru": "Lavash"},
            slug="contract-lavash",
            branches_count=12,
        )
        self.place = Place.objects.create(
            category=self.category,
            brand=self.brand,
            name={"ru": "Lavash", "tg": "Lavash", "en": "Lavash"},
            slug="contract-lavash-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            district="Сино",
            location=Point(68.747663, 38.548607, srid=4326),
            phones=["+992333444666"],
            website="https://instagram.com/lavash._tj",
            opening_hours={
                day: ["08:00", "22:00"]
                for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            },
            price_level=2,
            rating=4.6,
            reviews_count=128,
            status=Place.Status.PUBLISHED,
        )
        self.second_place = Place.objects.create(
            category=self.category,
            name={"ru": "Второе место", "tg": "Ҷои дуюм", "en": "Second place"},
            slug="contract-second-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            location=Point(68.760000, 38.560000, srid=4326),
            price_level=4,
            rating=3.2,
            reviews_count=10,
            status=Place.Status.PUBLISHED,
        )
        self.photo = PlacePhoto.objects.create(
            place=self.place,
            image="places/contract-tz.jpg",
            credit="2GIS",
        )

    def test_pagination_contract_keeps_old_fields(self):
        response = self.client.get("/api/v1/places/?limit=1&page=1")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"], data["results"])
        self.assertEqual(data["total"], data["count"])
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["limit"], 1)

    def test_search_is_typo_tolerant(self):
        response = self.client.get("/api/v1/places/?q=Lavsh")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(
            response.json()["items"][0]["slug"],
            self.place.slug,
        )

    def test_public_filter_aliases(self):
        by_q = self.client.get("/api/v1/places/?q=Lavash")
        self.assertEqual(by_q.status_code, 200)
        self.assertEqual(by_q.json()["total"], 1)

        by_rating = self.client.get("/api/v1/places/?rating_min=4")
        self.assertEqual(by_rating.status_code, 200)
        self.assertEqual(by_rating.json()["total"], 1)

        by_price = self.client.get("/api/v1/places/?price=4")
        self.assertEqual(by_price.status_code, 200)
        self.assertEqual(by_price.json()["total"], 1)

        by_category_key = self.client.get(
            "/api/v1/places/?category=contract-restaurants"
        )
        self.assertEqual(by_category_key.status_code, 200)
        self.assertEqual(by_category_key.json()["total"], 2)

    def test_sort_aliases(self):
        best = self.client.get("/api/v1/places/?sort=best")
        self.assertEqual(best.status_code, 200)
        self.assertEqual(best.json()["items"][0]["slug"], self.place.slug)

        reviews = self.client.get("/api/v1/places/?sort=reviews")
        self.assertEqual(reviews.status_code, 200)
        self.assertEqual(reviews.json()["items"][0]["slug"], self.place.slug)

        invalid = self.client.get("/api/v1/places/?sort=unknown")
        self.assertEqual(invalid.status_code, 400)

    def test_radius_is_meters_with_legacy_km_alias(self):
        base = "/api/v1/places/?lat=38.548607&lon=68.747663"
        near = self.client.get(f"{base}&radius=5000")
        self.assertEqual(near.status_code, 200)
        self.assertEqual(near.json()["total"], 2)

        far = self.client.get(f"{base}&radius=100")
        self.assertEqual(far.status_code, 200)
        self.assertEqual(far.json()["total"], 1)

        legacy = self.client.get(f"{base}&radius_km=5")
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(legacy.json()["total"], 2)

    def test_detail_has_tz_fields(self):
        response = self.client.get(
            f"/api/v1/places/{self.place.slug}/?lang=ru"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["lat"], 38.548607)
        self.assertEqual(data["lon"], 68.747663)
        self.assertEqual(data["price"], 2)
        self.assertEqual(data["hours"]["mon"], ["08:00", "22:00"])
        self.assertEqual(data["brand"]["branches"], 12)
        self.assertEqual(data["photos"][0]["credit"], "2GIS")
        self.assertIn("/media/places/contract-tz.jpg", data["photos"][0]["url"])
        self.assertFalse(data["is_favorite"])

    def test_public_paths_work_without_trailing_slash(self):
        urls = [
            "/api/v1/categories",
            "/api/v1/places",
            "/api/v1/places/map?bbox=68.70,38.50,68.80,38.60",
            "/api/v1/home",
            "/api/v1/search/suggest?q=Lavash",
            f"/api/v1/places/{self.place.slug}",
            f"/api/v1/places/{self.place.slug}/similar",
            f"/api/v1/places/{self.place.slug}/claim",
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                if url.endswith("/claim"):
                    self.assertEqual(response.status_code, 401)
                else:
                    self.assertEqual(response.status_code, 200)

    def test_category_has_tz_sort_alias(self):
        response = self.client.get("/api/v1/categories/")
        self.assertEqual(response.status_code, 200)
        category = next(
            item for item in response.json()
            if item["key"] == self.category.key
        )
        self.assertEqual(category["sort"], 7)

    def test_map_items_have_coordinates(self):
        response = self.client.get(
            "/api/v1/places/map/?bbox=68.70,38.50,68.80,38.60"
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 2)
        item = next(
            place for place in data["results"]
            if place["slug"] == self.place.slug
        )
        self.assertEqual(item["lat"], 38.548607)
        self.assertEqual(item["lon"], 68.747663)


class AuthAndFavoritesContractTZTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(
            username="+992900000201",
            phone="+992900000201",
            name="Contract User",
        )
        self.other_user = User.objects.create_user(
            username="+992900000202",
            phone="+992900000202",
        )
        self.category = Category.objects.create(
            key="auth-contract",
            slug="auth-contract",
            name={"ru": "Кафе"},
        )
        self.place = Place.objects.create(
            category=self.category,
            name={"ru": "Тест"},
            slug="auth-contract-place",
            address={"ru": "Душанбе"},
            status=Place.Status.PUBLISHED,
        )

    def test_send_code_and_verify_no_slash(self):
        phone = "+992900000203"
        send = self.client.post(
            "/api/v1/auth/send-code",
            {"phone": phone},
            format="json",
        )
        self.assertEqual(send.status_code, 200)

        PhoneOTP.objects.create(
            phone=phone,
            code_hash=make_password("1234"),
            expires_at=timezone.now() + timedelta(minutes=3),
        )
        verify = self.client.post(
            "/api/v1/auth/verify",
            {"phone": phone, "code": "1234"},
            format="json",
        )
        self.assertEqual(verify.status_code, 200)
        self.assertIn("access", verify.json())
        self.assertIn("refresh", verify.json())

    def test_profile_me_no_slash(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["phone"], self.user.phone)

    def test_me_favorites_get_post_delete(self):
        self.client.force_authenticate(user=self.user)
        url = "/api/v1/me/favorites"

        created = self.client.post(
            url,
            {"place_id": self.place.id},
            format="json",
        )
        self.assertEqual(created.status_code, 201)

        listed = self.client.get(url)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)

        deleted = self.client.delete(
            url,
            {"place_id": self.place.id},
            format="json",
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(
            Favorite.objects.filter(
                user=self.user,
                place=self.place,
            ).exists()
        )

    def test_claim_by_slug_no_slash(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/api/v1/places/{self.place.slug}/claim",
            {"document_url": "https://example.com/patent.jpg"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Claim.objects.filter(
                place=self.place,
                user=self.user,
                status=Claim.Status.PENDING,
            ).exists()
        )
