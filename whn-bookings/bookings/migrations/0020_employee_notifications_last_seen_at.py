from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0019_clientlead_created_at_updated_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='employee',
            name='notifications_last_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
