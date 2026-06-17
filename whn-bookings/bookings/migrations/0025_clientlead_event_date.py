from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0024_remove_clientlead_email'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientlead',
            name='event_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]