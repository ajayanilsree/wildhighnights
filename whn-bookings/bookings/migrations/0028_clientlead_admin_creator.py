from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0027_bookingexpense_borne_by'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='clientlead',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='leads', to='bookings.employee'),
        ),
        migrations.AddField(
            model_name='clientlead',
            name='created_by_admin',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='clientlead',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='crm_entries_created', to=settings.AUTH_USER_MODEL),
        ),
    ]
