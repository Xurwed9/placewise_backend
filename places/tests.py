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

from places.models import Category, Place, Favorite, PlacePhoto, Claim, Brand
from places.management.commands.import_places import get_or_create_brand
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
        response = self.client.get("/api/v1/me/favorites")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), [])

    def test_favorites_support_page_limit_pagination(self):
        Favorite.objects.create(user=self.user, place=self.place)

        response = self.client.get(
            "/api/v1/me/favorites?page=1&limit=1"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["page"], 1)
        self.assertEqual(response.data["limit"], 1)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["place"], self.place.id)

    def test_add_favorite(self):
        response = self.client.post(
            "/api/v1/me/favorites",
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
        url = "/api/v1/me/favorites"
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
            "/api/v1/me/favorites",
            {"place": self.place.id},
            format="json",
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

    def test_me_favorites_alias_lists_and_deletes(self):
        Favorite.objects.create(user=self.user, place=self.place)

        list_response = self.client.get("/api/v1/me/favorites")

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.json()), 1)

        delete_response = self.client.delete(
            "/api/v1/me/favorites",
            {"place": self.place.id},
            format="json",
        )

        self.assertEqual(
            delete_response.status_code,
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

        response = self.client.get("/api/v1/me/favorites")

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )




    def test_add_favorite_with_missing_place(self):
        response = self.client.post(
            "/api/v1/me/favorites",
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
            "/api/v1/me/favorites",
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
        self.assertEqual(place.status, Place.Status.PUBLISHED)
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

    def test_get_or_create_brand_creates_brand(self):
        brand = get_or_create_brand(
        name="Dodo Pizza",
        branches=9,
        external_url="https://dodopizza.tj",
        )
        self.assertEqual(Brand.objects.count(), 1)
        self.assertEqual(brand.name["ru"], "Dodo Pizza")
        self.assertEqual(brand.branches_count, 9)
        self.assertEqual(brand.website, "https://dodopizza.tj")

    def test_get_or_create_brand_reuses_existing_brand(self):
        first = get_or_create_brand(
            name="Dodo Pizza",
            branches=3,
        )
        second = get_or_create_brand(
            name="Dodo Pizza",
            branches=9,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Brand.objects.count(), 1)
        self.assertEqual(second.branches_count, 9)

    def test_get_or_create_brand_matches_normalized_name(self):
        first = get_or_create_brand(
            name="Dodo Pizza",
            branches=3,
        )
        second = get_or_create_brand(
            name="  DODO   PIZZA  ",
            branches=9,
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Brand.objects.count(), 1)

    def test_2gis_import_creates_place_and_connects_brand(self):
        headers = [
            "name",
            "subcategory",
            "address",
            "phone",
            "opening_hours",
            "website_or_instagram",
            "lat",
            "lon",
            "rating",
            "reviews",
            "branches",
            "source",
        ]

        row = {
            "name": "Dodo Pizza",
            "subcategory": "pizza",
            "address": "Хиёбони Рӯдакӣ, 156",
            "phone": "+992 446100000",
            "opening_hours": "09:00-01:00",
            "website_or_instagram": "https://dodopizza.tj",
            "lat": "38.588296",
            "lon": "68.785423",
            "rating": "0",
            "reviews": "0",
            "branches": "9",
            "source": (
                "https://2gis.tj/dushanbe/firm/"
                "70000001100988348"
            ),
        }

        with self.csv_path.open(
            "w", encoding="utf-8", newline=""
        ) as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            writer.writerow(row)

        self.run_import()

        place = Place.objects.get(
            source="test-source",
            source_id="70000001100988348",
        )

        self.assertIsNotNone(place.brand)
        self.assertEqual(place.brand.name["ru"], "Dodo Pizza")
        self.assertEqual(place.brand.branches_count, 9)
        self.assertEqual(place.brand.website, "https://dodopizza.tj")




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

    @override_settings()
    def test_tz_uploads_path_and_image_field(self):
        with self.settings(MEDIA_ROOT=self.media_dir):
            self.client.force_authenticate(user=self.user)

            response = self.client.post(
                "/api/v1/uploads",
                {"image": self.make_image()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["format"], "webp")

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

    def test_owner_can_manage_place_photos(self):
        self.place.owner = self.user
        self.place.save(update_fields=["owner"])
        self.client.force_authenticate(user=self.user)

        with self.settings(MEDIA_ROOT=self.media_dir):
            upload = self.client.post(
                f"/api/v1/owner/places/{self.place.id}/photos",
                {"image": self.make_image()},
                format="multipart",
            )

            self.assertEqual(upload.status_code, 201, upload.data)
            photo_id = upload.data["id"]

            listing = self.client.get(
                f"/api/v1/owner/places/{self.place.id}/photos"
            )
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(len(listing.data), 1)

            delete = self.client.delete(
                f"/api/v1/owner/places/{self.place.id}/photos/{photo_id}/"
            )

        self.assertEqual(delete.status_code, 204)
        self.assertFalse(PlacePhoto.objects.filter(id=photo_id).exists())

    def test_non_owner_cannot_manage_place_photos(self):
        other = get_user_model().objects.create_user(
            username="photo_non_owner",
            phone="+992900000299",
            name="Non Owner",
        )
        self.client.force_authenticate(user=other)

        with self.settings(MEDIA_ROOT=self.media_dir):
            response = self.client.post(
                f"/api/v1/owner/places/{self.place.id}/photos",
                {"image": self.make_image()},
                format="multipart",
            )

        self.assertEqual(response.status_code, 403)

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
            self.assertEqual(place["status"], "hidden")
            self.assertEqual(place["status_internal"], "draft")


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



    def test_admin_can_filter_places_by_tz_status(self):
        active_place = Place.objects.create(
            category=self.category,
            name={"ru": "Активное", "tg": "Фаъол", "en": "Active"},
            slug="crud-active-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
        )

        response = self.client.get(
            "/api/v1/admin/places/?status=active"
        )

        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data["results"]]
        self.assertIn(active_place.id, ids)
        self.assertNotIn(self.place.id, ids)
        self.assertTrue(
            all(item["status_tz"] == "active"
                for item in response.data["results"])
        )

    def test_admin_can_update_place_with_tz_status(self):
        response = self.client.patch(
            f"/api/v1/admin/places/{self.place.id}/",
            {"status_tz": "active"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status_tz"], "active")

        self.place.refresh_from_db()
        self.assertEqual(self.place.status, Place.Status.PUBLISHED)


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

    def test_admin_can_create_place_with_tz_status(self):
        self.client.force_authenticate(user=self.admin)
        payload = dict(self.payload)
        payload["slug"] = "new-cafe-active-test"
        payload["status_tz"] = "active"

        response = self.client.post(
            self.url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status_tz"], "active")

        place = Place.objects.get(slug="new-cafe-active-test")
        self.assertEqual(place.status, Place.Status.PUBLISHED)

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
            f"/api/v1/places/{self.place.slug}/claim",
            {
                "document_url": "https://example.com/document.pdf",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_user_can_create_claim(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            f"/api/v1/places/{self.place.slug}/claim",
            {
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
            f"/api/v1/places/{self.place.slug}/claim",
            {
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
            any(
                item["id"] == self.claim.id
                for item in response.json()["items"]
            )
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
                for item in response.json()["items"]
            )
        )

    def test_admin_can_approve_claim_and_assign_owner(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/v1/admin/claims/",
            {"claim_id": self.claim.id, "action": "approve"},
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
            "/api/v1/admin/claims/",
            {"claim_id": self.claim.id, "action": "reject"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, Claim.Status.PENDING)

    def test_admin_can_reject_claim_with_reason(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/v1/admin/claims/",
            {
                "claim_id": self.claim.id,
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
            "/api/v1/admin/claims/",
            {"claim_id": self.claim.id, "action": "approve"},
            format="json",
        )
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(
            "/api/v1/admin/claims/",
            {
                "claim_id": self.claim.id,
                "action": "reject",
                "reason": "Сабаб",
            },
            format="json",
        )

        self.assertEqual(second_response.status_code, 400)

    def test_unknown_claim_returns_404(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/v1/admin/claims/",
            {"claim_id": 999999, "action": "approve"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

    def test_invalid_action_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            "/api/v1/admin/claims/",
            {"claim_id": self.claim.id, "action": "maybe"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)



class AdminImport2GISAPITests(TestCase):
    url = "/api/v1/admin/import/2gis/"

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()

        self.admin = User.objects.create_user(
            username="import_2gis_admin",
            phone="+992900000091",
            password="TestPass123!",
            role="admin",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="import_2gis_user",
            phone="+992900000092",
            password="TestPass123!",
        )

        self.category = Category.objects.create(
            key="api-import-test",
            slug="api-import-test",
            name={
                "ru": "Тестовая категория",
                "tg": "Категорияи санҷишӣ",
                "en": "Test category",
            },
            is_active=True,
        )

        self.csv_content = (
            "name,subcategory,address,phone,opening_hours,"
            "website_or_instagram,lat,lon,rating,reviews,branches,source\n"
            "API Test Cafe,cafe,Dushanbe,+992900000000,"
            "09:00-22:00,,38.5598,68.7870,4.5,120,1,"
            "https://2gis.com/firm/12345678901234567/\n"
        ).replace("\n", "\r\n").encode("utf-8")

    def make_csv(self, filename="places.csv", content=None):
        return SimpleUploadedFile(
            filename,
            content if content is not None else self.csv_content,
            content_type="text/csv",
        )

    def test_guest_cannot_import(self):
        response = self.client.post(
            self.url,
            {"file": self.make_csv()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 401)

    def test_regular_user_cannot_import(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            self.url,
            {"file": self.make_csv()},
            format="multipart",
        )

        self.assertEqual(response.status_code, 403)

    def test_non_csv_file_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {"file": self.make_csv(filename="places.txt")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)

    def test_dry_run_does_not_create_place(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "file": self.make_csv(),
                "category": self.category.key,
                "source": "2gis",
                "dry_run": "true",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertTrue(response.json()["dry_run"])
        self.assertEqual(
            response.json()["counts"]["created"],
            1,
        )
        self.assertFalse(
            Place.objects.filter(
                source="2gis",
                source_id="12345678901234567",
            ).exists()
        )

    def test_admin_can_import_csv(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            {
                "file": self.make_csv(),
                "category": self.category.key,
                "source": "2gis",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(response.json()["dry_run"])

        place = Place.objects.get(
            source="2gis",
            source_id="12345678901234567",
        )
        self.assertEqual(place.name["ru"], "API Test Cafe")
        self.assertEqual(place.category, self.category)
        self.assertEqual(place.status, Place.Status.PUBLISHED)

    def test_reimport_does_not_create_duplicate(self):
        self.client.force_authenticate(user=self.admin)

        for _ in range(2):
            response = self.client.post(
                self.url,
                {
                    "file": self.make_csv(),
                    "category": self.category.key,
                    "source": "2gis",
                },
                format="multipart",
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["success"])

        self.assertEqual(
            Place.objects.filter(
                source="2gis",
                source_id="12345678901234567",
            ).count(),
            1,
        )


    def test_mixed_valid_and_invalid_rows_report_partial_success(self):
        self.client.force_authenticate(user=self.admin)

        csv_content = (
            "name,subcategory,address,phone,opening_hours,"
            "website_or_instagram,lat,lon,rating,reviews,branches,source\n"
            "Valid Cafe,cafe,Dushanbe,+992900000000,"
            "09:00-22:00,,38.5598,68.7870,4.5,120,1,"
            "https://2gis.com/firm/12345678901234567/\n"
            "Invalid Cafe,cafe,,+992900000001,"
            "09:00-22:00,,38.5598,68.7870,4.0,10,1,"
            "https://2gis.com/firm/12345678901234568/\n"
        ).replace("\n", "\r\n").encode("utf-8")

        response = self.client.post(
            self.url,
            {
                "file": self.make_csv(content=csv_content),
                "category": self.category.key,
                "source": "2gis",
            },
            format="multipart",
        )

        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["success"])
        self.assertTrue(data["partial_success"])
        self.assertEqual(data["counts"]["created"], 1)
        self.assertEqual(data["counts"]["errors"], 1)

        self.assertTrue(
            Place.objects.filter(
                source="2gis",
                source_id="12345678901234567",
            ).exists()
        )
        self.assertFalse(
            Place.objects.filter(
                source="2gis",
                source_id="12345678901234568",
            ).exists()
        )


class OwnerPlaceUpdateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_user(
            username="+992900000041",
            phone="+992900000041",
            name="Owner",
            role="owner",
        )
        cls.other_user = get_user_model().objects.create_user(
            username="+992900000042",
            phone="+992900000042",
            name="Other",
        )
        cls.category = Category.objects.create(
            key="owner-update-category",
            slug="owner-update-category",
            name={"ru": "Кафе"},
        )
        cls.place = Place.objects.create(
            category=cls.category,
            name={"ru": "Место владельца"},
            slug="owner-update-place",
            address={"ru": "Душанбе"},
            phones=["+992900000041"],
            opening_hours={"mon": ["08:00", "22:00"]},
            owner=cls.owner,
            status=Place.Status.PUBLISHED,
        )

    def setUp(self):
        self.client = APIClient()

    def make_image(self):
        buffer = BytesIO()
        image = Image.new("RGB", (100, 80), color="green")
        image.save(buffer, format="JPEG")

        return SimpleUploadedFile(
            "owner-photo.jpg",
            buffer.getvalue(),
            content_type="image/jpeg",
        )

    def test_owner_can_update_allowed_fields_and_add_photos(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {
                "about": {"ru": "Нав"},
                "phones": ["+992900000099"],
                "opening_hours": {"mon": ["09:00", "23:00"]},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)

        photo_response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {"photos": [self.make_image()]},
            format="multipart",
        )

        self.assertEqual(
            photo_response.status_code,
            200,
            photo_response.data,
        )

        self.place.refresh_from_db()

        self.assertEqual(self.place.about["ru"], "Нав")
        self.assertEqual(self.place.phones, ["+992900000099"])
        self.assertEqual(self.place.opening_hours["mon"], ["09:00", "23:00"])
        self.assertEqual(self.place.photos.count(), 1)

        photo = self.place.photos.get()
        self.assertEqual(photo.author, self.owner)
        self.assertEqual(photo.source, PlacePhoto.Source.OWNER)

    def test_owner_cannot_update_name_or_slug(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {
                "name": {"ru": "Взлом"},
                "slug": "hacked",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.place.refresh_from_db()
        self.assertEqual(self.place.name["ru"], "Место владельца")
        self.assertEqual(self.place.slug, "owner-update-place")

    def test_owner_can_remove_own_photo(self):
        photo = PlacePhoto.objects.create(
            place=self.place,
            author=self.owner,
            source=PlacePhoto.Source.OWNER,
            image=SimpleUploadedFile(
                "remove-me.jpg",
                b"test-image",
                content_type="image/jpeg",
            ),
        )

        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {"remove_photo_ids": [photo.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            PlacePhoto.objects.filter(id=photo.id).exists()
        )

    def test_owner_can_use_hours_and_phone_aliases(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {
                "hours": {"mon": ["10:00", "20:00"]},
                "phone": "992 90 000 00 99",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)

        self.place.refresh_from_db()
        self.assertEqual(
            self.place.opening_hours["mon"],
            ["10:00", "20:00"],
        )
        self.assertIn("+992900000099", self.place.phones)
        self.assertIn("+992900000041", self.place.phones)

    def test_owner_invalid_phone_is_rejected(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {"phones": ["not-a-phone"]},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_owner_removing_photo_deletes_files(self):
        photo = PlacePhoto.objects.create(
            place=self.place,
            author=self.owner,
            source=PlacePhoto.Source.OWNER,
            image=SimpleUploadedFile(
                "remove-file.jpg",
                b"test-image",
                content_type="image/jpeg",
            ),
            thumbnail=SimpleUploadedFile(
                "remove-file-thumb.jpg",
                b"test-thumbnail",
                content_type="image/jpeg",
            ),
        )
        image_path = Path(photo.image.path)
        thumbnail_path = Path(photo.thumbnail.path)
        self.assertTrue(image_path.exists())
        self.assertTrue(thumbnail_path.exists())

        self.client.force_authenticate(user=self.owner)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {"remove_photo_ids": [photo.id]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Path(image_path).exists())
        self.assertFalse(Path(thumbnail_path).exists())

    def test_owner_places_are_paginated(self):
        Place.objects.create(
            category=self.category,
            name={"ru": "Второе место"},
            slug="owner-update-place-2",
            address={"ru": "Душанбе"},
            owner=self.owner,
            status=Place.Status.PUBLISHED,
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.get("/api/v1/owner/places?page=1&limit=1")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["limit"], 1)
        self.assertEqual(len(response.data["items"]), 1)

    def test_non_owner_cannot_update_place(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.patch(
            f"/api/v1/owner/places/{self.place.id}",
            {"about": {"ru": "Чужое"}},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
