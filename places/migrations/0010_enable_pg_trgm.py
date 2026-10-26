from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


INDEX_SQL = """
CREATE INDEX IF NOT EXISTS places_place_name_trgm
    ON places_place USING gin ((name::text) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_place_address_trgm
    ON places_place USING gin ((address::text) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_place_subcategory_trgm
    ON places_place USING gin ((subcategory::text) gin_trgm_ops);
"""

DROP_SQL = """
DROP INDEX IF EXISTS places_place_name_trgm;
DROP INDEX IF EXISTS places_place_address_trgm;
DROP INDEX IF EXISTS places_place_subcategory_trgm;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("places", "0009_place_status_closed"),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(INDEX_SQL, DROP_SQL),
    ]
