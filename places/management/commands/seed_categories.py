from django.core.management.base import BaseCommand

from places.models import Category
from places.translations import CATEGORY_SEED


class Command(BaseCommand):
    help = "Create or update the nine starting categories from the technical spec"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving anything",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        totals = {"created": 0, "updated": 0, "skipped": 0}

        for item in CATEGORY_SEED:
            key = item["key"]
            slug = item["slug"]

            category = Category.objects.filter(key=key).first()
            if category is None:
                category = Category.objects.filter(slug=slug).first()
                if category is not None and category.key != key:
                    totals["skipped"] += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped {key}: slug '{slug}' is already used "
                            f"by category '{category.key}'"
                        )
                    )
                    continue

            if dry_run:
                totals["updated" if category else "created"] += 1
                continue

            is_new = category is None
            if is_new:
                category = Category(
                    key=key,
                    slug=slug,
                    is_active=True,
                )

            current_name = dict(category.name or {})
            for language, value in item["name"].items():
                if not current_name.get(language):
                    current_name[language] = value

            category.name = current_name
            category.icon = category.icon or item["icon"]
            category.sort_order = item["sort_order"]
            category.save()

            totals["created" if is_new else "updated"] += 1

        mode = "DRY RUN" if dry_run else "SEED"
        self.stdout.write(f"Mode: {mode}")
        for name, value in totals.items():
            self.stdout.write(f"  {name}: {value}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS("Dry run finished. No database changes were made.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("Categories are ready."))
