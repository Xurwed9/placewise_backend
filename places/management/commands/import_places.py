import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import URLValidator
from django.db import IntegrityError, transaction
from django.utils.text import slugify

from core.hours import parse_hours_text
from places.models import Brand, Category, Place
from places.translations import (
    resolve_category_key_from_filename,
    translate_subcategory,
)


# Формати нав аз ТЗ.
REQUIRED_COLUMNS = {
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
}

# Барои мутобиқат бо CSV-и кӯҳна ва тестҳои мавҷуда.
LEGACY_COLUMNS = {
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
    """Normalize recognizable Tajik phone numbers."""
    original = value.strip()
    digits = re.sub(r"\D", "", original)

    if digits.startswith("992") and len(digits) == 12:
        national = digits[3:]
    elif len(digits) == 10 and digits.startswith("8"):
        national = digits[1:]
    elif len(digits) == 9 and digits.startswith("9"):
        national = digits
    else:
        return original

    if len(national) != 9:
        return original

    return (
        f"+992 {national[:2]} {national[2:5]} "
        f"{national[5:7]} {national[7:]}"
    )


def extract_2gis_id(source_url):
    """Extract a numeric firm ID from a 2GIS firm URL."""
    if not source_url:
        raise ValueError("source URL is empty")

    try:
        URLValidator(schemes=["http", "https"])(source_url)
    except ValidationError as exc:
        raise ValueError("Invalid source URL") from exc

    parsed = urlparse(source_url)
    host = (parsed.hostname or "").lower()

    allowed_hosts = (
        "2gis.com",
        "2gis.tj",
    )

    if not any(
        host == domain or host.endswith("." + domain)
        for domain in allowed_hosts
    ):
        raise ValueError("source must be a 2GIS URL")

    match = re.search(r"/firm/(\d+)", parsed.path, re.IGNORECASE)
    if not match:
        raise ValueError("Could not extract firm ID from source URL")

    return match.group(1)


def parse_hours(value):
    """Parse opening hours and preserve ambiguous source text for review."""
    raw = value.strip()
    if not raw:
        return {}, []

    hours, warnings = parse_hours_text(raw)

    if hours is None:
        return {
            "raw": raw,
            "needs_manual_review": True,
        }, warnings

    return hours, warnings


def parse_row(row, legacy=False):
    name = row.get("name", "").strip()
    address = row.get("address", "").strip()

    if not name:
        raise ValueError("name is empty")
    if not address:
        raise ValueError("address is empty")

    if legacy:
        source_id = row.get("source_id", "").strip()
        if not source_id:
            raise ValueError("source_id is empty")
        source_url = ""
        external_url = row.get("website", "").strip()
    else:
        source_url = row.get("source", "").strip()
        source_id = extract_2gis_id(source_url)
        external_url = row.get("website_or_instagram", "").strip()

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

    if external_url:
        try:
            URLValidator(schemes=["http", "https"])(external_url)
        except ValidationError as exc:
            raise ValueError("Invalid website_or_instagram URL") from exc

    phones = [
        normalize_phone(phone)
        for phone in re.split(r"[,;]", row.get("phone", ""))
        if phone.strip()
    ]

    hours, hour_warnings = parse_hours(row.get("opening_hours", ""))
    subcategory = translate_subcategory(row.get("subcategory", ""))

    warnings = list(hour_warnings)
    if subcategory and not subcategory.get("tg"):
        warnings.append("Subcategory translation needs manual review")

    return {
        "source_id": source_id,
        "source_url": source_url,
        "name": name,
        "subcategory": subcategory,
        "address": address,
        "phones": phones,
        "opening_hours": hours,
        "external_url": external_url,
        "is_instagram": (
            "instagram.com" in (urlparse(external_url).hostname or "").lower()
            if external_url
            else False
        ),
        "lat": lat,
        "lon": lon,
        "rating": rating,
        "reviews": reviews,
        "branches": branches,
        "warnings": warnings,
    }


def get_or_create_brand(name, branches, external_url=""):
    """Find a matching brand by normalized name or create one."""
    normalized_name = " ".join(name.casefold().split())
    base_slug = slugify(name)[:190] or "brand"

    # Prefer an existing brand with the same Russian display name.
    for brand in Brand.objects.all().only("id", "name", "slug", "branches_count", "website", "instagram"):
        existing_name = " ".join(
            str(brand.name.get("ru", "")).casefold().split()
        )
        if existing_name == normalized_name:
            if branches > brand.branches_count:
                brand.branches_count = branches
            if external_url:
                if "instagram.com" in external_url.lower():
                    brand.instagram = external_url
                else:
                    brand.website = external_url
            brand.save()
            return brand

    slug = base_slug
    suffix = 2
    while Brand.objects.filter(slug=slug).exists():
        slug = f"{base_slug[:185]}-{suffix}"
        suffix += 1

    brand = Brand.objects.create(
        name={"ru": name},
        slug=slug,
        branches_count=branches,
    )

    if external_url:
        if "instagram.com" in external_url.lower():
            brand.instagram = external_url
        else:
            brand.website = external_url
        brand.save(update_fields=["instagram", "website"])

    return brand


class Command(BaseCommand):
    help = "Import or update places from a 2GIS CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument(
            "--category",
            default=None,
            help="Category key/slug; by default derived from the CSV filename",
        )
        parser.add_argument("--source", default="2gis")
        parser.add_argument(
            "--status",
            choices=[
                Place.Status.DRAFT,
                Place.Status.PUBLISHED,
                Place.Status.HIDDEN,
            ],
            default=Place.Status.PUBLISHED,
            help="Status for newly imported places (default: published)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report without saving changes",
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
        status = options["status"]
        category_key = (
            options["category"].strip()
            if options["category"]
            else resolve_category_key_from_filename(csv_path.name)
        )
        dry_run = options["dry_run"]

        report_path = (
            Path(options["report"]).resolve()
            if options["report"]
            else csv_path.with_name(f"{csv_path.stem}_import_report.csv")
        )

        if report_path == csv_path:
            raise CommandError("Report path must differ from input CSV")
        if not source:
            raise CommandError("--source cannot be empty")
        if not csv_path.is_file():
            raise CommandError(f"CSV file not found: {csv_path}")

        if not category_key:
            available = ", ".join(
                Category.objects.order_by("key").values_list("key", flat=True)
            )
            raise CommandError(
                f"Could not determine category from filename '{csv_path.name}'. "
                "Use --category with one of the available keys: "
                f"{available or 'run seed_categories first'}"
            )

        category = (
            Category.objects.filter(key=category_key).first()
            or Category.objects.filter(slug=category_key).first()
        )
        if category is None:
            raise CommandError(
                f"Category '{category_key}' not found. "
                "Use --category to specify the category key or slug."
            )
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
            with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                if not reader.fieldnames:
                    raise CommandError("CSV has no header")

                reader.fieldnames = [
                    field.strip() if field else ""
                    for field in reader.fieldnames
                ]
                if len(reader.fieldnames) != len(set(reader.fieldnames)):
                    raise CommandError("CSV contains duplicate column names")

                columns = set(reader.fieldnames)
                if REQUIRED_COLUMNS <= columns:
                    legacy = False
                elif LEGACY_COLUMNS <= columns:
                    legacy = True
                else:
                    missing_new = REQUIRED_COLUMNS - columns
                    raise CommandError(
                        "CSV does not match the supported format. "
                        "Missing new-format columns: "
                        + ", ".join(sorted(missing_new))
                    )

                self.stdout.write(f"Category: {category.key}")
                self.stdout.write(f"Source: {source}")
                self.stdout.write(f"Status: {status}")
                self.stdout.write(f"Format: {'legacy' if legacy else '2GIS'}")
                self.stdout.write(f"Mode: {'DRY RUN' if dry_run else 'IMPORT'}")

                for line_number, raw_row in enumerate(reader, start=2):
                    row = {
                        (key or "").strip(): (value or "").strip()
                        for key, value in raw_row.items()
                        if key is not None
                    }
                    raw_id = row.get("source_id", "")
                    raw_name = row.get("name", "")

                    try:
                        data = parse_row(row, legacy=legacy)
                    except ValueError as exc:
                        totals["errors"] += 1
                        add_report(line_number, raw_id, raw_name, "error", str(exc))
                        self.stderr.write(
                            self.style.ERROR(f"Line {line_number}: {exc}")
                        )
                        continue

                    source_id = data["source_id"]
                    if source_id in seen_ids:
                        totals["skipped"] += 1
                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            "skipped",
                            f"Duplicate source_id '{source_id}' within this CSV",
                        )
                        continue
                    seen_ids.add(source_id)

                    warnings = list(data["warnings"])
                    if any(not phone.startswith("+992 ") for phone in data["phones"]):
                        warnings.append("Phone format needs manual review")

                    if data["branches"] >= 2:
                        warnings.append(
                            "Brand association will be inferred from the place name"
                        )

                    existing = Place.objects.filter(
                        source=source,
                        source_id=source_id,
                    ).first()
                    action = "updated" if existing else "created"

                    if dry_run:
                        totals[action] += 1
                        totals["warnings"] += len(warnings)
                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            f"would_{action}",
                            "; ".join(warnings),
                        )
                        continue

                    try:
                        with transaction.atomic():
                            place = (
                                Place.objects.select_for_update()
                                .filter(source=source, source_id=source_id)
                                .first()
                            )
                            is_new = place is None

                            if is_new:
                                base_slug = slugify(data["name"])[:240] or "place"
                                slug = base_slug
                                suffix = 2
                                while Place.objects.filter(slug=slug).exists():
                                    slug = f"{base_slug[:230]}-{suffix}"
                                    suffix += 1
                                place = Place(
                                    slug=slug,
                                    source=source,
                                    source_id=source_id,
                                    status=status,
                                )

                            place.category = category
                            existing_name = (
                                place.name
                                if isinstance(place.name, dict)
                                else {}
                            )
                            place.name = {
                                **existing_name,
                                "ru": data["name"],
                            }

                            if data["subcategory"]:
                                place.subcategory = data["subcategory"]

                            existing_address = (
                                place.address
                                if isinstance(place.address, dict)
                                else {}
                            )
                            place.address = {
                                **existing_address,
                                "ru": data["address"],
                            }
                            place.phones = data["phones"]
                            place.location = Point(
                                float(data["lon"]),
                                float(data["lat"]),
                                srid=4326,
                            )
                            place.ext_rating = data["rating"]
                            place.ext_reviews = data["reviews"]

                            if data["opening_hours"]:
                                place.opening_hours = data["opening_hours"]

                            if data["external_url"]:
                                place.website = data["external_url"]

                            if data["branches"] >= 2:
                                place.brand = get_or_create_brand(
                                    data["name"],
                                    data["branches"],
                                    data["external_url"],
                                )

                            place.save()

                        action = "created" if is_new else "updated"
                        totals[action] += 1
                        totals["warnings"] += len(warnings)
                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            action,
                            "; ".join(warnings),
                        )

                    except (IntegrityError, ValidationError, ValueError) as exc:
                        totals["errors"] += 1
                        message = f"Database save failed: {exc}"
                        add_report(
                            line_number,
                            source_id,
                            data["name"],
                            "error",
                            message,
                        )
                        self.stderr.write(
                            self.style.ERROR(f"Line {line_number}: {message}")
                        )

        except (OSError, UnicodeError, csv.Error) as exc:
            raise CommandError(f"Cannot read CSV: {exc}") from exc

        try:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("w", encoding="utf-8-sig", newline="") as report_file:
                writer = csv.DictWriter(report_file, fieldnames=REPORT_COLUMNS)
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
                self.style.SUCCESS("Dry run finished. No database changes were made.")
            )
        elif totals["errors"]:
            raise CommandError(
                "Import completed with errors. Successful rows may already "
                "have been saved. Review the CSV report before retrying."
            )
        else:
            self.stdout.write(self.style.SUCCESS("Import completed successfully."))
