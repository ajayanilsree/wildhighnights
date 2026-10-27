"""User-approved configuration correction; never infer or backfill historical rates."""
from decimal import Decimal
from django.db import migrations


def correct_esani(apps, schema_editor):
    Artist = apps.get_model('bookings', 'Artist')
    # Compare-and-set: do not overwrite settings already independently corrected/edited.
    Artist.objects.using(schema_editor.connection.alias).filter(
        name__iexact='Esani', sales_commission_percentage=Decimal('20.00'),
        lead_commission_percentage=Decimal('15.00'),
    ).update(sales_commission_percentage=Decimal('80.00'), lead_commission_percentage=Decimal('85.00'))


class Migration(migrations.Migration):
    dependencies = [('bookings', '0031_booking_applied_artist_percentage_and_more')]
    operations = [migrations.RunPython(correct_esani, migrations.RunPython.noop)]
