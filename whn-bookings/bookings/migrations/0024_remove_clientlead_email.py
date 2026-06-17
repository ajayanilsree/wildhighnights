from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0023_clientlead_status_conversion_states'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='clientlead',
            name='email',
        ),
    ]