from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0028_clientlead_admin_creator'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientlead',
            name='event_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
