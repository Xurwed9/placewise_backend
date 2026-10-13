
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from places.models import Category, Place


REQUIRED_COLUMNS = {
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
}


class Command(BaseCommand):
    help = "Import places from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument("--category", required=True)
        parser.add_argument("--source", default="2gis")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate without saving data",
        )

    def handle(self, *args, **options):
        csv_file = Path(options["csv_file"])
        source = options["source"].strip()
        category_key = options["category"].strip()

        if not csv_file.is_file():
            raise CommandError(f"File not found: {csv_file}")

        with csv_file.open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise CommandError("CSV has no header.")

            reader.fieldnames = [
                name.strip() if name else ""
                for name in reader.fieldnames
            ]

            missing = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise CommandError(
                    "Missing columns: "
                    + ", ".join(sorted(missing))
                )

            rows = [
                {
                    (key or "").strip(): (value or "").strip()
                    for key, value in row.items()
                    if key is not None
                }
                for row in reader
            ]

        category = Category.objects.filter(
            key=category_key
        ).first()

        if category is None:
            category = Category.objects.filter(
                slug=category_key
            ).first()

        if category is None:
            raise CommandError(
                f"Category '{category_key}' not found."
            )

        if not category.is_active:
            raise CommandError(
                f"Category '{category_key}' is inactive."
            )

        errors = []
        source_ids = set()

        for line, row in enumerate(rows, start=2):
            try:
                source_id = row["source_id"]
                name = row["name"]
                address = row["address"]

                if not source_id:
                    raise ValueError("source_id is empty")
                if not name:
                    raise ValueError("name is empty")
                if not address:
                    raise ValueError("address is empty")
                if source_id in source_ids:
                    raise ValueError(
                        f"Duplicate source_id: {source_id}"
                    )

                source_ids.add(source_id)

                lat = Decimal(row["lat"])
                lon = Decimal(row["lon"])
                rating = Decimal(row["rating"])
                reviews = int(row["reviews"])
                branches = int(row["branches"])

                if not lat.is_finite() or not -90 <= lat <= 90:
                    raise ValueError("Invalid latitude")
                if not lon.is_finite() or not -180 <= lon <= 180:
                    raise ValueError("Invalid longitude")
                if not rating.is_finite() or not 0 <= rating <= 5:
                    raise ValueError("Rating must be from 0 to 5")
                if reviews < 0:
                    raise ValueError("Reviews cannot be negative")
                if branches < 1:
                    raise ValueError("Branches must be at least 1")

            except (
                ValueError,
                TypeError,
                KeyError,
                InvalidOperation,
            ) as exc:
                errors.append(f"Line {line}: {exc}")

        self.stdout.write(f"Category: {category.key}")
        self.stdout.write(f"Total rows: {len(rows)}")

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))

            raise CommandError(
                f"Validation failed: {len(errors)} error(s). "
                "Nothing was imported."
            )

        if options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run passed. No data was saved."
                )
            )
            return

        created = 0
        updated = 0

        with transaction.atomic():
            for row in rows:
                source_id = row["source_id"]

                place = Place.objects.filter(
                    source=source,
                    source_id=source_id,
                ).first()

                is_new = place is None

                if is_new:
                    base_slug = slugify(row["name"]) or "place"
                    slug = base_slug
                    suffix = 2

                    while Place.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{suffix}"
                        suffix += 1

                    place = Place(
                        slug=slug,
                        source=source,
                        source_id=source_id,
                        status=Place.Status.DRAFT,
                    )

                phones = [
                    phone.strip()
                    for phone in row["phone"].replace(";", ",").split(",")
                    if phone.strip()
                ]

                opening_hours_text = row["opening_hours"]

                place.category = category
                place.name = {"ru": row["name"]}
                place.subcategory = (
                    {"ru": row["subcategory"]}
                    if row["subcategory"]
                    else {}
                )
                place.address = {"ru": row["address"]}
                place.phones = phones
                place.website = row["website"]
                place.location = Point(
                    float(row["lon"]),
                    float(row["lat"]),
                    srid=4326,
                )
                place.ext_rating = Decimal(row["rating"])
                place.ext_reviews = int(row["reviews"])

                # Keep the original hours instead of guessing
                # the opening schedule for each weekday.
                place.opening_hours = (
                    {"raw": opening_hours_text}
                    if opening_hours_text
                    else {}
                )

                place.save()

                if is_new:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: created={created}, "
                f"updated={updated}, total={len(rows)}"
            )
        )
