from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from places.models import Category
from places.translations import CATEGORY_SEED


class SeedCategoriesCommandTests(TestCase):
    def run_seed(self, dry_run=False):
        output = StringIO()
        args = ["--dry-run"] if dry_run else []
        call_command("seed_categories", *args, stdout=output)
        return output.getvalue()

    def test_creates_nine_categories_with_all_translations(self):
        self.run_seed()

        self.assertEqual(Category.objects.count(), len(CATEGORY_SEED))
        for item in CATEGORY_SEED:
            category = Category.objects.get(key=item["key"])
            self.assertEqual(category.slug, item["slug"])
            self.assertEqual(category.name, item["name"])
            self.assertTrue(category.is_active)
            self.assertEqual(category.sort_order, item["sort_order"])

    def test_repeated_run_is_idempotent(self):
        self.run_seed()
        output = self.run_seed()

        self.assertEqual(Category.objects.count(), len(CATEGORY_SEED))
        self.assertIn("created: 0", output)
        self.assertIn("updated: 9", output)

    def test_dry_run_does_not_create_categories(self):
        output = self.run_seed(dry_run=True)

        self.assertEqual(Category.objects.count(), 0)
        self.assertIn("created: 9", output)

    def test_fills_missing_translations_without_overwriting_existing(self):
        category = Category.objects.create(
            key="restaurants",
            slug="restaurants",
            name={"ru": "Мои рестораны"},
        )

        self.run_seed()

        category.refresh_from_db()
        self.assertEqual(category.name["ru"], "Мои рестораны")
        self.assertEqual(category.name["tg"], "Тарабхонаҳо")
        self.assertEqual(category.name["en"], "Restaurants")
