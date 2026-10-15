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
