from decimal import Decimal

from django.db import migrations, models
from django.utils.text import slugify


def configure_esani(apps, schema_editor):
    Artist = apps.get_model('bookings', 'Artist')
    artist = Artist.objects.filter(name__iexact='Esani').order_by('pk').first()
    if artist is None:
        base_slug = slugify('Esani')
        slug = base_slug
        suffix = 1
        while Artist.objects.filter(slug=slug).exists():
            slug = f'{base_slug}-{suffix}'
            suffix += 1
        artist = Artist(name='Esani', slug=slug, genre='')
    artist.sales_commission_percentage = Decimal('20.00')
    artist.lead_commission_percentage = Decimal('15.00')
    artist.save()


def keep_rates_on_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('bookings', '0029_clientlead_event_date'),
    ]

    operations = [
        migrations.AddField(
            model_name='artist',
            name='sales_commission_percentage',
            field=models.DecimalField(decimal_places=2, default=Decimal('85.00'), max_digits=5),
        ),
        migrations.AddField(
            model_name='artist',
            name='lead_commission_percentage',
            field=models.DecimalField(decimal_places=2, default=Decimal('90.00'), max_digits=5),
        ),
        migrations.RunPython(configure_esani, keep_rates_on_reverse),
    ]
