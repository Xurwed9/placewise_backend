import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from places.models import Category, Place
from places.translations import (
    resolve_category_key_from_filename,
    translate_subcategory,
)


HEADERS = [
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


def make_row(**overrides):
    row = {
        "name": "Lavash",
        "subcategory": "Быстрое питание",
        "address": "улица Маяковского, 89/1",
        "phone": "+992 333 44 46 66",
        "opening_hours": "09:00-22:00",
        "website_or_instagram": "https://instagram.com/lavash._tj",
        "lat": "38.548607",
        "lon": "68.747663",
        "rating": "4.6",
        "reviews": "128",
        "branches": "12",
        "source": "https://2gis.tj/dushanbe/firm/70000001100988348",
    }
    row.update(overrides)
    return row


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


class TranslationHelperTests(SimpleTestCase):
    def test_resolves_category_from_cyrillic_filenames(self):
        cases = {
            "01_Рестораны.csv": "restaurants",
            "02_Аптеки.csv": "pharmacies",
            "03_Супермаркеты.csv": "supermarkets",
            "04_Цветы.csv": "flowers",
            "05_Выпечка.csv": "bakery",
            "06_Электроника.csv": "electronics",
            "07_Красота.csv": "beauty",
            "08_Павербанки.csv": "powerbanks",
            "09_Дом и уход.csv": "home_care",
        }

        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    resolve_category_key_from_filename(filename),
                    expected,
                )

    def test_unknown_filename_returns_none(self):
        self.assertIsNone(
            resolve_category_key_from_filename("places.csv")
        )

    def test_translates_russian_and_english_subcategories(self):
        self.assertEqual(
            translate_subcategory("Быстрое питание"),
            {
                "ru": "Быстрое питание",
                "tg": "Хӯроки тез",
                "en": "Fast food",
            },
        )
        self.assertEqual(
            translate_subcategory("cafe"),
            {
                "ru": "Кафе",
                "tg": "Қаҳвахона",
                "en": "Cafe",
            },
        )

    def test_unknown_subcategory_keeps_original_russian_text(self):
        self.assertEqual(
            translate_subcategory("Неизвестная категория"),
            {"ru": "Неизвестная категория"},
        )


class Import2GISTZTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.csv_path = Path(self.temp_dir.name) / "01_Рестораны.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_import(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        call_command(
            "import_places",
            str(self.csv_path),
            *args,
            stdout=stdout,
            stderr=stderr,
        )
        return stdout.getvalue(), stderr.getvalue()

    def test_import_uses_category_from_filename(self):
        call_command("seed_categories", stdout=StringIO())
        write_csv(self.csv_path, [make_row()])

        output, _ = self.run_import("--source", "test-source")

        place = Place.objects.get(
            source="test-source",
            source_id="70000001100988348",
        )
        self.assertEqual(place.category.key, "restaurants")
        self.assertEqual(
            place.subcategory,
            {
                "ru": "Быстрое питание",
                "tg": "Хӯроки тез",
                "en": "Fast food",
            },
        )
        self.assertEqual(place.status, Place.Status.PUBLISHED)
        self.assertIn("Category: restaurants", output)

        response = APIClient().get(f"/api/v1/places/{place.slug}/")
        self.assertEqual(response.status_code, 200)

    def test_unknown_filename_raises_clear_error(self):
        call_command("seed_categories", stdout=StringIO())
        unknown_path = Path(self.temp_dir.name) / "places.csv"
        write_csv(unknown_path, [make_row()])

        with self.assertRaisesMessage(
            CommandError,
            "Could not determine category from filename",
        ):
            call_command(
                "import_places",
                str(unknown_path),
                "--source",
                "test-source",
                stdout=StringIO(),
                stderr=StringIO(),
            )

    def test_status_option_controls_new_places(self):
        call_command("seed_categories", stdout=StringIO())
        write_csv(self.csv_path, [make_row()])

        self.run_import("--source", "test-source", "--status", "hidden")

        place = Place.objects.get(
            source="test-source",
            source_id="70000001100988348",
        )
        self.assertEqual(place.status, Place.Status.HIDDEN)

    def test_unknown_subcategory_is_reported_for_review(self):
        call_command("seed_categories", stdout=StringIO())
        write_csv(
            self.csv_path,
            [make_row(subcategory="Неизвестная категория")],
        )
        report_path = Path(self.temp_dir.name) / "report.csv"

        self.run_import(
            "--source",
            "test-source",
            "--report",
            str(report_path),
        )

        place = Place.objects.get(
            source="test-source",
            source_id="70000001100988348",
        )
        self.assertEqual(
            place.subcategory,
            {"ru": "Неизвестная категория"},
        )

        with report_path.open(
            "r", encoding="utf-8-sig", newline=""
        ) as report_file:
            report_rows = list(csv.DictReader(report_file))

        self.assertIn(
            "Subcategory translation needs manual review",
            report_rows[0]["message"],
        )


    def test_reimport_preserves_existing_translations_and_normalizes_phone(self):
        call_command("seed_categories", stdout=StringIO())
        write_csv(self.csv_path, [make_row()])
        self.run_import("--source", "test-source")

        place = Place.objects.get(
            source="test-source",
            source_id="70000001100988348",
        )
        place.name["tg"] = "Лаваш"
        place.name["en"] = "Lavash"
        place.address["tg"] = "кӯчаи Маяковский"
        place.save(update_fields=["name", "address"])

        write_csv(
            self.csv_path,
            [
                make_row(
                    name="Lavash Updated",
                    phone="8 333 44 46 66",
                )
            ],
        )
        self.run_import("--source", "test-source")

        place.refresh_from_db()
        self.assertEqual(place.name["ru"], "Lavash Updated")
        self.assertEqual(place.name["tg"], "Лаваш")
        self.assertEqual(place.name["en"], "Lavash")
        self.assertEqual(place.address["ru"], "улица Маяковского, 89/1")
        self.assertEqual(place.address["tg"], "кӯчаи Маяковский")
        self.assertEqual(place.phones, ["+992 33 344 46 66"])


class AdminImport2GISFilenameCategoryTests(TestCase):
    url = "/api/v1/admin/import/2gis/"

    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="filename_import_admin",
            phone="+992900000093",
            password="TestPass123!",
            role="admin",
            is_staff=True,
        )
        self.client.force_authenticate(user=self.admin)
        call_command("seed_categories", stdout=StringIO())

    def test_api_resolves_category_from_uploaded_filename(self):
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerow(make_row())
        content = buffer.getvalue().encode("utf-8")

        response = self.client.post(
            self.url,
            {
                "file": SimpleUploadedFile(
                    "01_Рестораны.csv",
                    content,
                    content_type="text/csv",
                ),
                "source": "2gis",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["category"], "restaurants")

        place = Place.objects.get(
            source="2gis",
            source_id="70000001100988348",
        )
        self.assertEqual(place.category.key, "restaurants")
        self.assertEqual(place.status, Place.Status.PUBLISHED)
        self.assertEqual(place.subcategory["tg"], "Хӯроки тез")
