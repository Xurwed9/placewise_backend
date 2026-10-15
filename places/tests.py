import csv
import tempfile
from pathlib import Path
from io import StringIO
from decimal import Decimal
from io import BytesIO
import tempfile
import shutil

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from rest_framework import status
from django.core.files.storage import default_storage

from places.models import Category, Place, Favorite, PlacePhoto, Claim
from reviews.models import Review

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

    def test_published_place_detail_includes_photos(self):
        category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="photo-api-test-category",
            key="photo_api_test_category",
            is_active=True,
        )

        place = Place.objects.create(
            category=category,
            name={"ru": "Тест кафе", "tg": "Кафеи тестӣ", "en": "Test Cafe"},
            slug="photo-api-test-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
        )

        buffer = BytesIO()
        image = Image.new("RGB", (120, 90), color="blue")
        image.save(buffer, format="JPEG")

        photo = PlacePhoto.objects.create(
            place=place,
            image=SimpleUploadedFile(
                "test-photo.jpg",
                buffer.getvalue(),
                content_type="image/jpeg",
            ),
            alt={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            sort_order=1,
            is_cover=True,
        )

        response = self.client.get(
            f"/api/v1/places/{place.slug}/?lang=ru"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("photos", data)
        self.assertEqual(len(data["photos"]), 1)
        self.assertEqual(data["photos"][0]["id"], photo.id)
        self.assertIn("image", data["photos"][0])
        self.assertTrue(data["photos"][0]["image"])

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




    def test_add_favorite_with_missing_place(self):
        response = self.client.post(
            "/api/v1/favorites/",
            {"place": 999999},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Favorite.objects.count(), 0)

    def test_add_unpublished_place_to_favorites(self):
        draft_place = Place.objects.create(
            category=self.category,
            name={"ru": "Черновик"},
            slug="favorite-test-draft-place",
            address={"ru": "Душанбе"},
            status=Place.Status.DRAFT,
        )

        response = self.client.post(
            "/api/v1/favorites/",
            {"place": draft_place.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(
            Favorite.objects.filter(
                user=self.user,
                place=draft_place,
            ).exists()
        )




class ImportPlacesCommandTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            key="import-test",
            slug="import-test",
            name={
                "ru": "Тестовая категория",
                "tg": "Категорияи санҷишӣ",
                "en": "Test category",
            },
            is_active=True,
        )

        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp_dir.name) / "places.csv"

        self.headers = [
            "source_id",
            "name",
            "subcategory",
            "address",
            "phone",
            "opening_hours",
            "website",
            "lat",
            "lon",
            "rating",
            "reviews",
            "branches",
        ]

        self.row = {
            "source_id": "test-123",
            "name": "Test Cafe",
            "subcategory": "cafe",
            "address": "Dushanbe",
            "phone": "+992900000000",
            "opening_hours": "09:00-22:00",
            "website": "https://example.com",
            "lat": "38.5598",
            "lon": "68.7870",
            "rating": "4.5",
            "reviews": "120",
            "branches": "1",
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_csv(self, rows):
        with self.csv_path.open(
            "w", encoding="utf-8", newline=""
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=self.headers,
            )
            writer.writeheader()
            writer.writerows(rows)

    def run_import(self, dry_run=False):
        output = StringIO()

        args = [
            str(self.csv_path),
            "--category",
            self.category.key,
            "--source",
            "test-source",
        ]

        if dry_run:
            args.append("--dry-run")

        call_command(
            "import_places",
            *args,
            stdout=output,
        )

        return output.getvalue()

    def test_import_creates_place(self):
        self.write_csv([self.row])

        self.run_import()

        place = Place.objects.get(
            source="test-source",
            source_id="test-123",
        )

        self.assertEqual(place.name["ru"], "Test Cafe")
        self.assertEqual(place.status, Place.Status.DRAFT)
        self.assertEqual(place.ext_rating, 4.5)
        self.assertEqual(place.ext_reviews, 120)

    def test_reimport_updates_without_duplicate(self):
        self.write_csv([self.row])
        self.run_import()

        updated_row = {
            **self.row,
            "name": "Updated Test Cafe",
            "rating": "4.8",
        }

        self.write_csv([updated_row])
        self.run_import()

        self.assertEqual(
            Place.objects.filter(
                source="test-source",
                source_id="test-123",
            ).count(),
            1,
        )

        place = Place.objects.get(
            source="test-source",
            source_id="test-123",
        )

        self.assertEqual(place.name["ru"], "Updated Test Cafe")
        self.assertEqual(place.ext_rating, Decimal("4.8"))


    def test_duplicate_source_id_in_csv_is_skipped(self):
        duplicate_row = {
            **self.row,
            "name": "Duplicate Test Cafe",
        }

        self.write_csv([self.row, duplicate_row])

        output = self.run_import()

        self.assertIn("created: 1", output)
        self.assertIn("skipped: 1", output)
        self.assertEqual(
            Place.objects.filter(
                source="test-source",
                source_id="test-123",
            ).count(),
            1,
        )


    def test_report_file_contains_duplicate_warning(self):
        duplicate_row = {
            **self.row,
            "name": "Duplicate Test Cafe",
        }
        self.write_csv([self.row, duplicate_row])

        report_path = Path(self.temp_dir.name) / "report.csv"

        call_command(
            "import_places",
            str(self.csv_path),
            "--category",
            self.category.key,
            "--source",
            "test-source",
            "--report",
            str(report_path),
            stdout=StringIO(),
        )

        with report_path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as report_file:
            report_rows = list(csv.DictReader(report_file))

        self.assertEqual(len(report_rows), 2)
        self.assertEqual(report_rows[0]["status"], "created")
        self.assertEqual(report_rows[1]["status"], "skipped")
        self.assertIn(
            "Duplicate source_id",
            report_rows[1]["message"],
        )



    def test_dry_run_does_not_create_place(self):
        self.write_csv([self.row])

        output = self.run_import(dry_run=True)

        self.assertIn("created: 1", output)
        self.assertEqual(
            Place.objects.filter(
                source="test-source",
                source_id="test-123",
            ).count(),
            0,
        )

    def test_hidden_status_is_preserved(self):
        self.write_csv([self.row])
        self.run_import()

        place = Place.objects.get(
            source="test-source",
            source_id="test-123",
        )
        place.status = Place.Status.HIDDEN
        place.save(update_fields=["status"])

        updated_row = {
            **self.row,
            "name": "Updated Hidden Cafe",
        }

        self.write_csv([updated_row])
        self.run_import()

        place.refresh_from_db()

        self.assertEqual(place.status, Place.Status.HIDDEN)
        self.assertEqual(place.name["ru"], "Updated Hidden Cafe")

    def test_invalid_row_is_reported(self):
        invalid_row = {
            **self.row,
            "lat": "not-a-coordinate",
        }

        self.write_csv([invalid_row])

        with self.assertRaises(CommandError):
            self.run_import()

        self.assertFalse(
            Place.objects.filter(
                source="test-source",
                source_id="test-123",
            ).exists()
        )




class UploadImageAPITests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_dir = tempfile.mkdtemp(
            prefix="placewise-test-media-"
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.user = User.objects.create_user(
            username="upload_test_user",
            phone="+992900000031",
            name="Upload Test User",
        )

        self.url = "/api/v1/uploads/"

    def make_image(self):
        buffer = BytesIO()
        image = Image.new("RGB", (120, 90), color="blue")
        image.save(buffer, format="JPEG")

        return SimpleUploadedFile(
            "photo.jpg",
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    @override_settings()
    def test_authenticated_user_can_upload_image(self):
        with self.settings(MEDIA_ROOT=self.media_dir):
            self.client.force_authenticate(user=self.user)

            response = self.client.post(
                self.url,
                {"file": self.make_image()},
                format="multipart",
            )

            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["format"], "webp")

            filename = response.json()["filename"]
            self.assertTrue(filename.endswith(".webp"))

            saved_path = f"uploads/{filename}"

            with default_storage.open(saved_path, "rb") as saved_file:
                with Image.open(saved_file) as saved_image:
                    self.assertEqual(saved_image.format, "WEBP")

    def test_guest_cannot_upload_image(self):
        response = self.client.post(
            self.url,
            {"file": self.make_image()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 401)

    def test_invalid_file_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        invalid_file = SimpleUploadedFile(
            "bad.jpg",
            b"not an actual image",
            content_type="image/jpeg",
        )

        response = self.client.post(
            self.url,
            {"file": invalid_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)

    def test_file_over_10mb_is_rejected(self):
        self.client.force_authenticate(user=self.user)

        large_file = SimpleUploadedFile(
            "large.jpg",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )

        response = self.client.post(
            self.url,
            {"file": large_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)




class AdminCategoryAPITests(TestCase):
    def test_admin_update_missing_category_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.list_url}999999/",
            {"icon": "restaurant"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_delete_missing_category_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            f"{self.list_url}999999/"
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_can_list_categories(self):
        Category.objects.create(**self.payload)
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.data), 1)

    def test_regular_user_cannot_update_or_delete_category(self):
        category = Category.objects.create(**self.payload)
        self.client.force_authenticate(user=self.user)

        update_response = self.client.patch(
            f"{self.list_url}{category.id}/",
            {"icon": "restaurant"},
            format="json",
        )

        delete_response = self.client.delete(
            f"{self.list_url}{category.id}/"
        )

        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)

        category.refresh_from_db()
        self.assertNotEqual(category.icon, "restaurant")
        self.assertTrue(
            Category.objects.filter(id=category.id).exists()
        )

    def test_cannot_delete_category_used_by_place(self):
        category = Category.objects.create(**self.payload)

        Place.objects.create(
            category=category,
            name={
                "ru": "Тестовое кафе",
                "tg": "Қаҳвахонаи тестӣ",
                "en": "Test Cafe",
            },
            slug="category-in-use-test-place",
            address={
                "ru": "Душанбе",
                "tg": "Душанбе",
                "en": "Dushanbe",
            },
            status=Place.Status.DRAFT,
        )

        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            f"{self.list_url}{category.id}/"
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(
            Category.objects.filter(id=category.id).exists()
        )
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="admin_test",
            phone="+992900000101",
            password="TestPassword123!",
            role="admin",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="user_test",
            phone="+992900000102",
            password="TestPassword123!",
            role="user",
            is_staff=False,
        )

        self.list_url = "/api/v1/admin/categories/"

        self.payload = {
            "name": {
                "ru": "Рестораны",
                "tg": "Тарабхонаҳо",
                "en": "Restaurants",
            },
            "slug": "restaurants-test",
            "key": "restaurants_test",
            "icon": "utensils",
            "is_active": True,
            "sort_order": 1,
        }

    def test_anonymous_cannot_access_categories(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_regular_user_cannot_create_category(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.list_url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            Category.objects.filter(key="restaurants_test").exists()
        )

    def test_admin_can_create_category(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.list_url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Category.objects.get(key="restaurants_test").name["tg"],
            "Тарабхонаҳо",
        )

    def test_admin_can_update_category(self):
        category = Category.objects.create(**self.payload)
        self.client.force_authenticate(user=self.admin)

        response = self.client.patch(
            f"{self.list_url}{category.id}/",
            {"icon": "restaurant"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        category.refresh_from_db()
        self.assertEqual(category.icon, "restaurant")

    def test_admin_can_delete_unused_category(self):
        category = Category.objects.create(**self.payload)
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            f"{self.list_url}{category.id}/"
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            Category.objects.filter(id=category.id).exists()
        )

    def test_admin_get_missing_category_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            f"{self.list_url}999999/"
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_translations_are_rejected(self):
        self.client.force_authenticate(user=self.admin)

        payload = {
            **self.payload,
            "name": {
                "ru": "Рестораны",
                "tg": "Тарабхонаҳо",
            },
        }

        response = self.client.post(
            self.list_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)




class AdminPlacePhotoAPITests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_dir = tempfile.mkdtemp(
            prefix="placewise-photo-test-"
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="photo_admin",
            phone="+992900000201",
            password="TestPassword123!",
            role="admin",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="photo_user",
            phone="+992900000202",
            password="TestPassword123!",
            role="user",
            is_staff=False,
        )

        self.category = Category.objects.create(
            name={
                "ru": "Кафе",
                "tg": "Қаҳвахона",
                "en": "Cafe",
            },
            slug="photo-test-cafes",
            key="photo_test_cafes",
            is_active=True,
            sort_order=1,
        )

        self.place = Place.objects.create(
            category=self.category,
            name={
                "ru": "Тестовое кафе",
                "tg": "Қаҳвахонаи тестӣ",
                "en": "Test Cafe",
            },
            slug="photo-test-cafe",
            address={
                "ru": "Душанбе",
                "tg": "Душанбе",
                "en": "Dushanbe",
            },
            status=Place.Status.DRAFT,
        )

        self.list_url = (
            f"/api/v1/admin/places/{self.place.id}/photos/"
        )

    def make_image(self, filename="photo.jpg"):
        buffer = BytesIO()
        image = Image.new("RGB", (120, 90), color="blue")
        image.save(buffer, format="JPEG")

        return SimpleUploadedFile(
            filename,
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    def test_anonymous_cannot_list_photos(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 401)

    def test_regular_user_cannot_upload_photo(self):
        self.client.force_authenticate(user=self.user)

        with self.settings(MEDIA_ROOT=self.media_dir):
            response = self.client.post(
                self.list_url,
                {"image": self.make_image()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(PlacePhoto.objects.count(), 0)

    def test_admin_can_upload_and_list_photo(self):
        self.client.force_authenticate(user=self.admin)

        with self.settings(MEDIA_ROOT=self.media_dir):
            response = self.client.post(
                self.list_url,
                {"image": self.make_image()},
                format="multipart",
            )

            self.assertEqual(response.status_code, 201)
            self.assertTrue(
                PlacePhoto.objects.filter(
                    place=self.place
                ).exists()
            )

            list_response = self.client.get(self.list_url)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

    def test_admin_can_update_photo_metadata(self):
        self.client.force_authenticate(user=self.admin)

        with self.settings(MEDIA_ROOT=self.media_dir):
            upload_response = self.client.post(
                self.list_url,
                {"image": self.make_image()},
                format="multipart",
            )

            self.assertEqual(upload_response.status_code, 201)
            photo_id = upload_response.json()["id"]

            response = self.client.patch(
                f"/api/v1/admin/photos/{photo_id}/",
                {"sort_order": 5},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)

        photo = PlacePhoto.objects.get(id=photo_id)
        self.assertEqual(photo.sort_order, 5)

    def test_admin_can_delete_photo(self):
        self.client.force_authenticate(user=self.admin)

        with self.settings(MEDIA_ROOT=self.media_dir):
            upload_response = self.client.post(
                self.list_url,
                {"image": self.make_image()},
                format="multipart",
            )

            self.assertEqual(upload_response.status_code, 201)
            photo_id = upload_response.json()["id"]

            response = self.client.delete(
                f"/api/v1/admin/photos/{photo_id}/"
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            PlacePhoto.objects.filter(id=photo_id).exists()
        )

    def test_missing_place_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            "/api/v1/admin/places/999999/photos/"
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_photo_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.delete(
            "/api/v1/admin/photos/999999/"
        )

        self.assertEqual(response.status_code, 404)



class AdminPlaceCRUDAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="place_crud_admin",
            phone="+992900000301",
            password="TestPassword123!",
            role="admin",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="place_crud_user",
            phone="+992900000302",
            password="TestPassword123!",
            role="user",
            is_staff=False,
        )

        self.client.force_authenticate(user=self.admin)

        self.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="crud-test-category",
            key="crud_test_category",
            is_active=True,
            sort_order=1,
        )

        self.place = Place.objects.create(
            category=self.category,
            name={"ru": "Кафе тест", "tg": "Қаҳвахонаи тестӣ", "en": "Test Cafe"},
            slug="crud-test-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.DRAFT,
        )      

    
    def test_admin_places_pagination_respects_page_size(self):
        Place.objects.create(
            category=self.category,
            name={"ru": "Кафе 1", "tg": "Кафе 1", "en": "Cafe 1"},
            slug="cafe-pagination-1",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.DRAFT,
        )

        Place.objects.create(
            category=self.category,
            name={"ru": "Кафе 2", "tg": "Кафе 2", "en": "Cafe 2"},
            slug="cafe-pagination-2",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.DRAFT,
        )

        response = self.client.get(
            "/api/v1/admin/places/?page_size=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])


    def test_admin_can_filter_places_by_status(self):
        response = self.client.get(
            "/api/v1/admin/places/?status=draft"
        )

        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.data["count"], 1)

        for place in response.data["results"]:
            self.assertEqual(place["status"], "draft")


    def test_admin_can_search_places_by_name(self):
        response = self.client.get(
            "/api/v1/admin/places/?search=Кафе"
        )

        self.assertEqual(response.status_code, 200)

        slugs = [
            place["slug"]
            for place in response.data["results"]
        ]

        self.assertIn("crud-test-place", slugs)


    def test_admin_can_update_place_location(self):
        response = self.client.patch(
            f"/api/v1/admin/places/{self.place.id}/",
            {
                "location": {
                    "type": "Point",
                    "coordinates": [68.7800, 38.5598],
                }
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)

        self.place.refresh_from_db()
        self.assertIsNotNone(self.place.location)
        self.assertAlmostEqual(self.place.location.x, 68.7800, places=4)
        self.assertAlmostEqual(self.place.location.y, 38.5598, places=4)

    
    def test_deleting_place_removes_photo_file(self):
        image = Image.new("RGB", (10, 10), color="red")
        image_bytes = BytesIO()
        image.save(image_bytes, format="JPEG")

        uploaded_image = SimpleUploadedFile(
            "place-test.jpg",
            image_bytes.getvalue(),
            content_type="image/jpeg",
        )

        photo = PlacePhoto.objects.create(
            place=self.place,
            image=uploaded_image,
            alt={"ru": "Тест", "tg": "Санҷиш", "en": "Test"},
        )

        image_path = photo.image.path
        self.assertTrue(Path(image_path).exists())

        response = self.client.delete(
            f"/api/v1/admin/places/{self.place.id}/"
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Path(image_path).exists())


    def test_admin_cannot_delete_place_with_review(self):
        Review.objects.create(
            user=self.user,
            place=self.place,
            rating=5,
            text="Хизматрасонии хуб",
            lang="tg",
        )

        response = self.client.delete(
            f"/api/v1/admin/places/{self.place.id}/"
        )

        self.assertEqual(response.status_code, 409)
        self.assertTrue(
            Place.objects.filter(id=self.place.id).exists()
        )

    def test_admin_can_list_places(self):
        response = self.client.get("/api/v1/admin/places/")
        self.assertEqual(response.status_code, 200)

    def test_admin_can_retrieve_place(self):
        response = self.client.get(
            f"/api/v1/admin/places/{self.place.id}/"
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_can_update_place(self):
        response = self.client.patch(
            f"/api/v1/admin/places/{self.place.id}/",
            {"name": {"ru": "Новое кафе", "tg": "Қаҳвахонаи нав", "en": "New Cafe"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.place.refresh_from_db()
        self.assertEqual(self.place.name["ru"], "Новое кафе")

    def test_regular_user_cannot_manage_places(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/v1/admin/places/")
        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_cannot_manage_places(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/admin/places/")
        self.assertEqual(response.status_code, 401)

    def test_admin_can_delete_place_without_reviews(self):
        response = self.client.delete(
            f"/api/v1/admin/places/{self.place.id}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            Place.objects.filter(id=self.place.id).exists()
        )



class AdminPlacePublishHideAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="publish_hide_admin",
            phone="+992900000401",
            password="TestPassword123!",
            role="admin",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="publish_hide_user",
            phone="+992900000402",
            password="TestPassword123!",
            role="user",
            is_staff=False,
        )

        self.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="publish-hide-category",
            key="publish_hide_category",
            is_active=True,
        )

        self.place = Place.objects.create(
            category=self.category,
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="publish-hide-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.DRAFT,
        )

        self.client.force_authenticate(user=self.admin)

    def test_admin_can_publish_place(self):
        response = self.client.post(
            f"/api/v1/admin/places/{self.place.id}/publish/"
        )
        self.assertEqual(response.status_code, 200)

        self.place.refresh_from_db()
        self.assertEqual(self.place.status, Place.Status.PUBLISHED)

    def test_publishing_already_published_place(self):
        self.place.status = Place.Status.PUBLISHED
        self.place.save()

        response = self.client.post(
            f"/api/v1/admin/places/{self.place.id}/publish/"
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_can_hide_place(self):
        self.place.status = Place.Status.PUBLISHED
        self.place.save()

        response = self.client.post(
            f"/api/v1/admin/places/{self.place.id}/hide/"
        )
        self.assertEqual(response.status_code, 200)

        self.place.refresh_from_db()
        self.assertEqual(self.place.status, Place.Status.HIDDEN)

    def test_hiding_already_hidden_place(self):
        self.place.status = Place.Status.HIDDEN
        self.place.save()

        response = self.client.post(
            f"/api/v1/admin/places/{self.place.id}/hide/"
        )
        self.assertEqual(response.status_code, 200)

    def test_regular_user_cannot_publish_or_hide(self):
        self.client.force_authenticate(user=self.user)

        publish_response = self.client.post(
            f"/api/v1/admin/places/{self.place.id}/publish/"
        )
        hide_response = self.client.post(
            f"/api/v1/admin/places/{self.place.id}/hide/"
        )

        self.assertEqual(publish_response.status_code, 403)
        self.assertEqual(hide_response.status_code, 403)

    def test_missing_place_returns_404(self):
        response = self.client.post(
            "/api/v1/admin/places/999999/publish/"
        )
        self.assertEqual(response.status_code, 404)



class AdminPlaceCreateAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="place_create_admin",
            phone="+992900000501",
            password="TestPassword123!",
            role="admin",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="place_create_user",
            phone="+992900000502",
            password="TestPassword123!",
            role="user",
            is_staff=False,
        )

        self.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="create-test-category",
            key="create_test_category",
            is_active=True,
        )

        self.url = "/api/v1/admin/places/"

        self.payload = {
            "name": {
                "ru": "Новое кафе",
                "tg": "Қаҳвахонаи нав",
                "en": "New Cafe",
            },
            "slug": "new-cafe-create-test",
            "category": self.category.id,
            "address": {
                "ru": "Душанбе",
                "tg": "Душанбе",
                "en": "Dushanbe",
            },
            "about": {
                "ru": "Описание кафе",
                "tg": "Тавсифи қаҳвахона",
                "en": "Cafe description",
            },
        }

    def test_admin_can_create_place(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Place.objects.filter(
                slug="new-cafe-create-test"
            ).exists()
        )

        place = Place.objects.get(slug="new-cafe-create-test")
        self.assertEqual(place.status, Place.Status.DRAFT)

    def test_regular_user_cannot_create_place(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_anonymous_user_cannot_create_place(self):
        response = self.client.post(
            self.url,
            self.payload,
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_create_place_requires_translations(self):
        self.client.force_authenticate(user=self.admin)

        invalid_payload = {
            **self.payload,
            "name": {"ru": "Только русский"},
        }

        response = self.client.post(
            self.url,
            invalid_payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Place.objects.filter(
                slug="new-cafe-create-test"
            ).exists()
        )

    def test_create_place_requires_category(self):
        self.client.force_authenticate(user=self.admin)

        invalid_payload = self.payload.copy()
        invalid_payload.pop("category")

        response = self.client.post(
            self.url,
            invalid_payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)




class AdminClaimAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="claim_admin",
            phone="+992900000081",
            password="TestPass123!",
            role="admin",
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="claim_regular",
            phone="+992900000082",
            password="TestPass123!",
        )
        self.owner_candidate = User.objects.create_user(
            username="claim_owner",
            phone="+992900000083",
            password="TestPass123!",
        )

        self.category = Category.objects.create(
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            slug="claim-test-category",
            key="claim_test_category",
            is_active=True,
        )

        self.place = Place.objects.create(
            category=self.category,
            name={"ru": "Тест кафе", "tg": "Кафеи тестӣ", "en": "Test Cafe"},
            slug="claim-test-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
        )

        self.claim = Claim.objects.create(
            place=self.place,
            user=self.owner_candidate,
            document_url="https://example.com/document.pdf",
        )

    def test_guest_cannot_create_claim(self):
        response = self.client.post(
            "/api/v1/claims/",
            {
                "place": self.place.id,
                "document_url": "https://example.com/document.pdf",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_user_can_create_claim(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            "/api/v1/claims/",
            {
                "place": self.place.id,
                "document_url": "https://example.com/document.pdf",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            Claim.objects.filter(
                place=self.place,
                user=self.regular_user,
                status=Claim.Status.PENDING,
            ).count(),
            1,
        )

    def test_duplicate_pending_claim_is_rejected(self):
        self.client.force_authenticate(user=self.owner_candidate)

        response = self.client.post(
            "/api/v1/claims/",
            {
                "place": self.place.id,
                "document_url": "https://example.com/another.pdf",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_regular_user_cannot_list_claims(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/v1/admin/claims/")

        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_claims(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get("/api/v1/admin/claims/")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any(item["id"] == self.claim.id for item in response.json())
        )

    def test_admin_can_filter_claims_by_status(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            "/api/v1/admin/claims/?status=pending"
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            all(
                item["status"] == Claim.Status.PENDING
                for item in response.json()
            )
        )

    def test_admin_can_approve_claim_and_assign_owner(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/v1/admin/claims/{self.claim.id}/",
            {"action": "approve"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.claim.refresh_from_db()
        self.place.refresh_from_db()
        self.owner_candidate.refresh_from_db()

        self.assertEqual(self.claim.status, Claim.Status.APPROVED)
        self.assertEqual(self.place.owner, self.owner_candidate)
        self.assertEqual(
            self.owner_candidate.role,
            self.owner_candidate.Role.OWNER,
        )

    def test_reject_claim_requires_reason(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/v1/admin/claims/{self.claim.id}/",
            {"action": "reject"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.PENDING)

    def test_admin_can_reject_claim_with_reason(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/v1/admin/claims/{self.claim.id}/",
            {
                "action": "reject",
                "reason": "Ҳуҷҷатҳо нопурраанд.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.REJECTED)
        self.assertEqual(response.json()["reason"], "Ҳуҷҷатҳо нопурраанд.")

    def test_already_reviewed_claim_cannot_be_reviewed_again(self):
        self.client.force_authenticate(user=self.admin)

        first_response = self.client.post(
            f"/api/v1/admin/claims/{self.claim.id}/",
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(
            f"/api/v1/admin/claims/{self.claim.id}/",
            {"action": "reject", "reason": "Сабаб"},
            format="json",
        )

        self.assertEqual(second_response.status_code, 400)

    def test_unknown_claim_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/v1/admin/claims/999999/",
            {"action": "approve"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_action_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            f"/api/v1/admin/claims/{self.claim.id}/",
            {"action": "maybe"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


