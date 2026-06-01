from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0022_clientlead_conversion_booking_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientlead',
            name='status',
            field=models.CharField(
                choices=[
                    ('Follow-up Needed', 'Follow-up Needed'),
                    ('Converted', 'Converted'),
                    ('Converted - Pending Booking', 'Converted - Pending Booking'),
                    ('Converted - Booking Created', 'Converted - Booking Created'),
                    ('Not Interested', 'Not Interested'),
                ],
                default='Follow-up Needed',
                max_length=30,
            ),
        ),
    ]
