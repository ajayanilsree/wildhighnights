from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('bookings', '0020_employee_notifications_last_seen_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='activitylog',
            name='employee_name',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='related_record',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('employee', 'Employee')], default='admin', max_length=20),
        ),
        migrations.AddField(
            model_name='activitylog',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activity_logs', to=settings.AUTH_USER_MODEL),
        ),
    ]
