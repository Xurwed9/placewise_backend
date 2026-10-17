import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from users.permissions import IsPlacewiseAdmin


MAX_CSV_SIZE = 10 * 1024 * 1024  # 10 MB


@extend_schema(
    operation_id="admin_import_2gis",
    summary="Import places from 2GIS CSV",
    description="Upload a CSV file and import places. Admin access required.",
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "format": "binary",
                },
                "category": {
                    "type": "string",
                },
                "source": {
                    "type": "string",
                },
                "dry_run": {
                    "type": "boolean",
                },
            },
            "required": ["file"],
        }
    },
    responses={200: dict, 400: dict, 413: dict},
)
@api_view(["POST"])
@permission_classes([IsPlacewiseAdmin])
@parser_classes([MultiPartParser, FormParser])
def admin_import_2gis(request):
    """Import 2GIS CSV through the existing management command."""

    uploaded_file = request.FILES.get("file")
    if uploaded_file is None:
        return Response(
            {"detail": "CSV file is required in the 'file' field."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    filename = Path(uploaded_file.name).name
    if not filename.lower().endswith(".csv"):
        return Response(
            {"detail": "Only .csv files are accepted."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded_file.size == 0:
        return Response(
            {"detail": "Uploaded CSV file is empty."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if uploaded_file.size > MAX_CSV_SIZE:
        return Response(
            {"detail": "CSV file exceeds the 10 MB limit."},
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    category = request.data.get("category", "").strip()
    source = request.data.get("source", "2gis").strip() or "2gis"

    raw_dry_run = str(request.data.get("dry_run", "false")).lower()
    if raw_dry_run not in {"true", "false", "1", "0", "yes", "no"}:
        return Response(
            {"detail": "dry_run must be true or false."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    dry_run = raw_dry_run in {"true", "1", "yes"}

    with tempfile.TemporaryDirectory(prefix="placewise-2gis-") as temp_dir:
        temp_path = Path(temp_dir)
        csv_path = temp_path / filename
        report_path = temp_path / "import_report.csv"

        try:
            with csv_path.open("wb") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)

            output = []
            errors_output = []

            command_options = {
                "source": source,
                "dry_run": dry_run,
                "report": str(report_path),
                "stdout": _ListWriter(output),
                "stderr": _ListWriter(errors_output),
            }
            if category:
                command_options["category"] = category

            command_error = None
            try:
                call_command(
                    "import_places",
                    str(csv_path),
                    **command_options,
                )
            except CommandError as exc:
                command_error = str(exc)

            report_rows = []
            if report_path.is_file():
                with report_path.open(
                    "r", encoding="utf-8-sig", newline=""
                ) as report_file:
                    report_rows = list(csv.DictReader(report_file))


            counts = {
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
                "warnings": 0,
            }

            action_statuses = {
                "created",
                "updated",
                "would_created",
                "would_updated",
            }

            for row in report_rows:
                row_status = row.get("status", "")
                message = row.get("message", "").strip()

                if row_status in {"created", "would_created"}:
                    counts["created"] += 1
                elif row_status in {"updated", "would_updated"}:
                    counts["updated"] += 1
                elif row_status == "skipped":
                    counts["skipped"] += 1
                elif row_status == "error":
                    counts["errors"] += 1

                # Паёми duplicate warning ҳисоб намешавад.
                # Warning-ҳои сатрҳои коркардшуда ҳисоб мешаванд.
                if row_status in action_statuses and message:
                    counts["warnings"] += len(message.split("; "))

            has_successful_rows = (
                counts["created"] + counts["updated"] > 0
            )
            has_errors = command_error is not None or counts["errors"] > 0

            response_data = {
                "success": not has_errors,
                "partial_success": has_successful_rows and has_errors,
                "dry_run": dry_run,
                "category": category or Path(filename).stem,
                "source": source,
                "counts": counts,
                "rows": report_rows[:100],
                "rows_returned": min(len(report_rows), 100),
                "rows_total": len(report_rows),
                "output": "".join(output)[-4000:],
                "errors_output": "".join(errors_output)[-4000:],
            }

            if command_error:
                response_data["detail"] = command_error


            # Row-level errors are included in the report. Return the report
            # even when some rows failed so the admin can inspect the result.
            return Response(response_data, status=status.HTTP_200_OK)

        except OSError as exc:
            return Response(
                {"detail": f"Could not process uploaded CSV: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class _ListWriter:
    """Minimal file-like object for capturing management command output."""

    def __init__(self, target):
        self.target = target

    def write(self, value):
        self.target.append(str(value))
        return len(value)

    def flush(self):
        pass
