from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0021_activitylog_user_employee_role_related_record'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientlead',
            name='conversion_artist',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='converted_crm_entries', to='bookings.artist'),
        ),
        migrations.AddField(
            model_name='clientlead',
            name='conversion_booking',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='crm_conversion_entries', to='bookings.booking'),
        ),
        migrations.AddField(
            model_name='clientlead',
            name='conversion_deal_amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='clientlead',
            name='conversion_event_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
