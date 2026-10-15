
import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
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

REPORT_COLUMNS = [
    "line",
    "source_id",
    "name",
    "status",
    "message",
]


def normalize_phone(value):
    """Normalize Tajikistan phone numbers when the format is recognized."""
    original = value.strip()
    digits = re.sub(r"\D", "", original)

    if digits.startswith("992") and len(digits) == 12:
        national = digits[3:]
    elif len(digits) == 9 and digits.startswith("9"):
        national = digits
    else:
        return original

    return (
        f"+992 {national[:2]} {national[2:5]} "
        f"{national[5:7]} {national[7:]}"
    )


def parse_row(row):
    source_id = row.get("source_id", "").strip()
    name = row.get("name", "").strip()
    address = row.get("address", "").strip()

    if not source_id:
        raise ValueError("source_id is empty")
    if not name:
        raise ValueError("name is empty")
    if not address:
        raise ValueError("address is empty")

    try:
        lat = Decimal(row["lat"])
        lon = Decimal(row["lon"])
        rating = Decimal(row["rating"])
        reviews = int(row["reviews"])
        branches = int(row["branches"])
    except (InvalidOperation, ValueError, TypeError, KeyError) as exc:
        raise ValueError("One or more numeric fields are invalid") from exc

    if not lat.is_finite() or not Decimal("-90") <= lat <= Decimal("90"):
        raise ValueError("Latitude must be between -90 and 90")

    if not lon.is_finite() or not Decimal("-180") <= lon <= Decimal("180"):
        raise ValueError("Longitude must be between -180 and 180")

    if not rating.is_finite() or not Decimal("0") <= rating <= Decimal("5"):
        raise ValueError("External rating must be between 0 and 5")

    if reviews < 0:
        raise ValueError("External review count cannot be negative")

    if branches < 1:
        raise ValueError("Branches must be at least 1")

    website = row.get("website", "").strip()
    if website:
        try:
            URLValidator(schemes=["http", "https"])(website)
        except ValidationError as exc:
            raise ValueError("Invalid website URL") from exc

    phones = [
        normalize_phone(phone)
        for phone in re.split(r"[,;]", row.get("phone", ""))
        if phone.strip()
    ]

    return {
        "source_id": source_id,
        "name": name,
        "subcategory": row.get("subcategory", "").strip(),
        "address": address,
        "phones": phones,
        "opening_hours": row.get("opening_hours", "").strip(),
        "website": website,
        "lat": lat,
        "lon": lon,
        "rating": rating,
        "reviews": reviews,
        "branches": branches,
    }


class Command(BaseCommand):
    help = "Import or update places from a CSV file safely"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument("--category", required=True)
        parser.add_argument("--source", default="2gis")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate rows and report changes without saving",
        )
        parser.add_argument(
            "--report",
            type=str,
            default=None,
            help="Path for the CSV import report",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_file"]).resolve()
        source = options["source"].strip()
        category_key = options["category"].strip()
        dry_run = options["dry_run"]

        report_path = Path(options["report"]).resolve() if options["report"] else (
            csv_path.with_name(f"{csv_path.stem}_import_report.csv")
        )

        if report_path == csv_path:
            raise CommandError("Report path must differ from input CSV")

        if not source:
            raise CommandError("--source cannot be empty")

        if not csv_path.is_file():
            raise CommandError(f"CSV file not found: {csv_path}")

        category = (
            Category.objects.filter(key=category_key).first()
            or Category.objects.filter(slug=category_key).first()
        )

        if category is None:
            raise CommandError(f"Category '{category_key}' not found")

        if not category.is_active:
            raise CommandError(f"Category '{category_key}' is inactive")

        totals = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "warnings": 0,
        }
        report_rows = []
        seen_ids = set()

        def add_report(line, source_id, name, status, message=""):
            report_rows.append({
                "line": line,
                "source_id": source_id,
                "name": name,
                "status": status,
                "message": message,
            })

        try:
            with csv_path.open(
                "r", encoding="utf-8-sig", newline=""
            ) as csv_file:
                reader = csv.DictReader(csv_file)

                if not reader.fieldnames:
                    raise CommandError("CSV has no header")

                reader.fieldnames = [
                    field.strip() if field else ""
                    for field in reader.fieldnames
                ]

                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise CommandError("CSV contains duplicate column names")

                missing = REQUIRED_COLUMNS - set(reader.fieldnames)
                if missing:
                    raise CommandError(
                        "Missing columns: " + ", ".join(sorted(missing))
                    )

                self.stdout.write(f"Category: {category.key}")
                self.stdout.write(f"Source: {source}")
                self.stdout.write(
                    f"Mode: {'DRY RUN' if dry_run else 'IMPORT'}"
                )

                for line_number, raw_row in enumerate(reader, start=2):
                    row = {
                        (key or "").strip(): (value or "").strip()
                        for key, value in raw_row.items()
                        if key is not None
                    }

                    raw_source_id = row.get("source_id", "")
                    raw_name = row.get("name", "")

                    try:
                        data = parse_row(row)
                    except ValueError as exc:
                        totals["errors"] += 1
                        message = str(exc)
                        self.stderr.write(
                            self.style.ERROR(
                                f"Line {line_number}: {message}"
                            )
                        )
                        add_report(
                            line_number,
                            raw_source_id,
                            raw_name,
                            "error",
                            message,
                        )
                        continue

                    source_id = data["source_id"]

                    if source_id in seen_ids:
                        totals["skipped"] += 1
                        message = (
                            f"Duplicate source_id '{source_id}' "
                            "within this CSV"
                        )
                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            "skipped",
                            message,
                        )
                        continue

                    seen_ids.add(source_id)

                    row_warnings = []

                    if any(
                        not phone.startswith("+992 ")
                        for phone in data["phones"]
                    ):
                        row_warnings.append(
                            "Phone format needs manual review"
                        )

                    if data["branches"] >= 2:
                        row_warnings.append(
                            "Multiple branches reported; brand was not "
                            "inferred because the CSV has no brand identity"
                        )

                    existing = Place.objects.filter(
                        source=source,
                        source_id=source_id,
                    ).first()

                    action = "updated" if existing else "created"

                    if dry_run:
                        totals[action] += 1
                        if row_warnings:
                            totals["warnings"] += len(row_warnings)

                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            f"would_{action}",
                            "; ".join(row_warnings),
                        )
                        continue

                    try:
                        with transaction.atomic():
                            place = (
                                Place.objects.select_for_update()
                                .filter(
                                    source=source,
                                    source_id=source_id,
                                )
                                .first()
                            )

                            is_new = place is None

                            if is_new:
                                base_slug = (
                                    slugify(data["name"]) or "place"
                                )
                                slug = base_slug
                                suffix = 2

                                while Place.objects.filter(
                                    slug=slug
                                ).exists():
                                    slug = f"{base_slug}-{suffix}"
                                    suffix += 1

                                place = Place(
                                    slug=slug,
                                    source=source,
                                    source_id=source_id,
                                    status=Place.Status.DRAFT,
                                )

                            place.category = category
                            place.name = {"ru": data["name"]}
                            place.subcategory = (
                                {"ru": data["subcategory"]}
                                if data["subcategory"]
                                else {}
                            )
                            place.address = {"ru": data["address"]}
                            place.phones = data["phones"]
                            place.location = Point(
                                float(data["lon"]),
                                float(data["lat"]),
                                srid=4326,
                            )
                            place.ext_rating = data["rating"]
                            place.ext_reviews = data["reviews"]

                            if data["website"]:
                                place.website = data["website"]

                            if data["opening_hours"]:
                                place.opening_hours = {
                                    "raw": data["opening_hours"],
                                    "needs_manual_review": True,
                                }

                            # Do not infer a brand from the place name.
                            # Existing brand relations are left untouched.

                            place.save()

                        action = "created" if is_new else "updated"
                        totals[action] += 1

                        if row_warnings:
                            totals["warnings"] += len(row_warnings)

                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            action,
                            "; ".join(row_warnings),
                        )

                    except (
                        IntegrityError,
                        ValidationError,
                        ValueError,
                    ) as exc:
                        totals["errors"] += 1
                        message = f"Database save failed: {exc}"
                        self.stderr.write(
                            self.style.ERROR(
                                f"Line {line_number}: {message}"
                            )
                        )
                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            "error",
                            message,
                        )

        except (OSError, UnicodeError, csv.Error) as exc:
            raise CommandError(f"Cannot read CSV: {exc}") from exc

        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)

            with report_path.open(
                "w", encoding="utf-8-sig", newline=""
            ) as report_file:
                writer = csv.DictWriter(
                    report_file,
                    fieldnames=REPORT_COLUMNS,
                )
                writer.writeheader()
                writer.writerows(report_rows)

        except OSError as exc:
            raise CommandError(
                f"Could not write import report to {report_path}: {exc}"
            ) from exc

        self.stdout.write("")
        self.stdout.write("Import report:")
        for key, value in totals.items():
            self.stdout.write(f"  {key}: {value}")

        self.stdout.write(f"Detailed report: {report_path}")

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry run finished. No database changes were made."
                )
            )
        elif totals["errors"]:
            raise CommandError(
                "Import completed with errors. Successful rows may already "
                "have been saved. Review the CSV report before retrying."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS("Import completed successfully.")
            )
