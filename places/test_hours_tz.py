from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from core.hours import (
    format_hours_text,
    is_open_now,
    normalize_hours,
    parse_hours_text,
)
from places.models import Category, Place


class HoursParsingTests(TestCase):
    def test_parse_every_day(self):
        hours, warnings = parse_hours_text("ежедневно 08:00-22:00")
        self.assertIsInstance(hours, dict)
        self.assertEqual(hours["mon"], ["08:00", "22:00"])
        self.assertEqual(hours["sun"], ["08:00", "22:00"])
        self.assertEqual(warnings, [])

    def test_parse_weekdays(self):
        hours, warnings = parse_hours_text("пн-пт 09:00-18:00")
        self.assertEqual(hours["mon"], ["09:00", "18:00"])
        self.assertEqual(hours["fri"], ["09:00", "18:00"])
        self.assertNotIn("sat", hours)
        self.assertNotIn("sun", hours)
        self.assertEqual(warnings, [])

    def test_parse_round_the_clock(self):
        hours, warnings = parse_hours_text("круглосуточно")
        self.assertEqual(hours, "24/7")
        self.assertEqual(warnings, [])

    def test_parse_twenty_four_seven(self):
        hours, warnings = parse_hours_text("24/7")
        self.assertEqual(hours, "24/7")

    def test_parse_night_shift(self):
        hours, warnings = parse_hours_text("09:00-01:00")
        self.assertEqual(hours["mon"], ["09:00", "01:00"])
        self.assertEqual(hours["sun"], ["09:00", "01:00"])
        self.assertEqual(warnings, [])

    def test_parse_by_day_shortcuts(self):
        hours, warnings = parse_hours_text("пн, ср, пт 10:00-20:00")
        self.assertEqual(hours["mon"], ["10:00", "20:00"])
        self.assertEqual(hours["wed"], ["10:00", "20:00"])
        self.assertEqual(hours["fri"], ["10:00", "20:00"])
        self.assertNotIn("tue", hours)
        self.assertEqual(warnings, [])

    def test_parse_tajik_every_day(self):
        hours, warnings = parse_hours_text("ҳар рӯз 08:00–22:00")
        self.assertEqual(hours["mon"], ["08:00", "22:00"])
        self.assertEqual(warnings, [])

    def test_parse_multiple_intervals(self):
        hours, warnings = parse_hours_text("10:00-14:00, 15:00-20:00")
        self.assertEqual(
            hours["mon"],
            [["10:00", "14:00"], ["15:00", "20:00"]],
        )
        self.assertEqual(warnings, [])
        self.assertEqual(
            format_hours_text(hours, "ru"),
            "ежедневно 10:00–14:00, 15:00–20:00",
        )

    def test_parse_different_weekend_hours(self):
        hours, warnings = parse_hours_text(
            "пн-пт 09:00-18:00, сб-вс 10:00-16:00"
        )
        self.assertEqual(hours["mon"], ["09:00", "18:00"])
        self.assertEqual(hours["sun"], ["10:00", "16:00"])
        self.assertEqual(
            format_hours_text(hours, "ru"),
            "пн-пт 09:00–18:00; сб-вс 10:00–16:00",
        )
        self.assertEqual(warnings, [])

    def test_parse_russian_from_to(self):
        hours, warnings = parse_hours_text("ежедневно с 08:00 до 22:00")
        self.assertEqual(hours["mon"], ["08:00", "22:00"])
        self.assertEqual(warnings, [])

    def test_normalize_legacy_generic_hours(self):
        legacy = {
            "raw": "09:00-01:00",
            "open": "09:00",
            "close": "01:00",
            "needs_manual_review": False,
        }
        normalized = normalize_hours(legacy)
        self.assertEqual(normalized["mon"], ["09:00", "01:00"])
        self.assertEqual(normalized["sun"], ["09:00", "01:00"])

    def test_normalize_legacy_day_dict(self):
        legacy = {
            "mon": {"open": "09:00", "close": "18:00"},
            "tue": {"closed": True},
        }
        normalized = normalize_hours(legacy)
        self.assertEqual(normalized["mon"], ["09:00", "18:00"])
        self.assertEqual(normalized["tue"], [])

    def test_normalize_new_day_lists(self):
        normalized = normalize_hours({"mon": ["08:00", "22:00"]})
        self.assertEqual(normalized, {"mon": ["08:00", "22:00"]})

    def test_unparsed_hours_keep_raw_text(self):
        raw = "по предварительной записи"
        hours, warnings = parse_hours_text(raw)
        self.assertIsNone(hours)
        self.assertTrue(warnings)
        self.assertEqual(format_hours_text({"raw": raw}, "ru"), raw)

    def test_open_now_night_shift(self):
        hours, _ = parse_hours_text("09:00-01:00")
        self.assertTrue(
            is_open_now(
                hours,
                datetime(2026, 1, 1, 0, 30, tzinfo=ZoneInfo("Asia/Dushanbe")),
            )
        )
        self.assertFalse(
            is_open_now(
                hours,
                datetime(2026, 1, 1, 2, 0, tzinfo=ZoneInfo("Asia/Dushanbe")),
            )
        )

    def test_open_now_weekdays_only(self):
        hours, _ = parse_hours_text("пн-пт 09:00-18:00")
        # 2026-01-03 is Saturday
        self.assertFalse(
            is_open_now(
                hours,
                datetime(2026, 1, 3, 12, 0, tzinfo=ZoneInfo("Asia/Dushanbe")),
            )
        )

    def test_open_now_closed_day(self):
        self.assertFalse(
            is_open_now(
                {"mon": [], "tue": ["09:00", "18:00"]},
                datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo("Asia/Dushanbe")),
            )
        )

    def test_format_hours_text_everyday_ru(self):
        hours, _ = parse_hours_text("ежедневно 08:00-22:00")
        self.assertEqual(format_hours_text(hours, "ru"), "ежедневно 08:00–22:00")

    def test_format_hours_text_everyday_tg(self):
        hours, _ = parse_hours_text("ежедневно 08:00-22:00")
        self.assertEqual(format_hours_text(hours, "tg"), "ҳар рӯз 08:00–22:00")

    def test_format_hours_text_weekdays_ru(self):
        hours, _ = parse_hours_text("пн-пт 09:00-18:00")
        self.assertEqual(format_hours_text(hours, "ru"), "пн-пт 09:00–18:00")

    def test_format_hours_text_round_the_clock(self):
        self.assertEqual(format_hours_text("24/7", "ru"), "круглосуточно")

    def test_import_parses_every_day_and_publishes(self):
        category = Category.objects.create(
            key="import-hours",
            slug="import-hours",
            name={"ru": "Тест", "tg": "Санҷиш", "en": "Test"},
            is_active=True,
        )

        temp_dir = __import__("tempfile").TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        csv_path = __import__("pathlib").Path(temp_dir.name) / "01_Рестораны.csv"
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
            "name": "Hours Cafe",
            "subcategory": "кафе",
            "address": "Душанбе",
            "phone": "+992900000010",
            "opening_hours": "ежедневно 08:00-22:00",
            "website_or_instagram": "",
            "lat": "38.5598",
            "lon": "68.7870",
            "rating": "4.0",
            "reviews": "10",
            "branches": "1",
            "source": "https://2gis.tj/dushanbe/firm/70000000000000001",
        }
        import csv

        with csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            writer.writeheader()
            writer.writerow(row)

        call_command(
            "import_places",
            str(csv_path),
            "--category",
            category.key,
            stdout=StringIO(),
        )

        place = Place.objects.get(
            source="2gis",
            source_id="70000000000000001",
        )
        self.assertEqual(place.category_id, category.id)
        self.assertEqual(place.status, Place.Status.PUBLISHED)
        self.assertEqual(place.opening_hours["mon"], ["08:00", "22:00"])


class PlaceHoursApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.category = Category.objects.create(
            key="hours-api",
            slug="hours-api",
            name={"ru": "Кафе", "tg": "Қаҳвахона", "en": "Cafe"},
            is_active=True,
        )
        self.place = Place.objects.create(
            category=self.category,
            name={"ru": "Тест кафе", "tg": "Кафеи тестӣ", "en": "Test Cafe"},
            slug="hours-api-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
            opening_hours={
                "mon": ["08:00", "22:00"],
                "tue": ["08:00", "22:00"],
                "wed": ["08:00", "22:00"],
                "thu": ["08:00", "22:00"],
                "fri": ["08:00", "22:00"],
                "sat": ["08:00", "22:00"],
                "sun": ["08:00", "22:00"],
            },
        )

    def test_detail_includes_hours_text_and_open_now(self):
        response = self.client.get(f"/api/v1/places/{self.place.slug}/?lang=ru")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("hours_text", data)
        self.assertIn("open_now", data)
        self.assertEqual(data["hours_text"], "ежедневно 08:00–22:00")
        self.assertIn(data["open_now"], (True, False, None))

    def test_open_now_filter_uses_dushanbe_time(self):
        closed_place = Place.objects.create(
            category=self.category,
            name={"ru": "Закрыто", "tg": "Пӯшида", "en": "Closed"},
            slug="hours-api-closed-place",
            address={"ru": "Душанбе", "tg": "Душанбе", "en": "Dushanbe"},
            status=Place.Status.PUBLISHED,
            opening_hours={
                day: ["22:00", "23:00"]
                for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
            },
        )

        fixed_utc = datetime(2026, 10, 23, 5, 0, tzinfo=UTC)

        with patch("places.views.timezone.now", return_value=fixed_utc):
            open_response = self.client.get(
                "/api/v1/places/?open_now=true&category=hours-api"
            )
            closed_response = self.client.get(
                "/api/v1/places/?open_now=false&category=hours-api"
            )

        self.assertEqual(open_response.status_code, 200)
        self.assertEqual(closed_response.status_code, 200)

        open_ids = {item["id"] for item in open_response.json()["results"]}
        closed_ids = {item["id"] for item in closed_response.json()["results"]}

        self.assertIn(self.place.id, open_ids)
        self.assertNotIn(closed_place.id, open_ids)
        self.assertIn(closed_place.id, closed_ids)
        self.assertNotIn(self.place.id, closed_ids)

    def test_open_now_filter_rejects_invalid(self):
        response = self.client.get("/api/v1/places/?open_now=maybe")
        self.assertEqual(response.status_code, 400)

    def test_detail_hours_text_tajik(self):
        response = self.client.get(f"/api/v1/places/{self.place.slug}/?lang=tg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["hours_text"], "ҳар рӯз 08:00–22:00")
