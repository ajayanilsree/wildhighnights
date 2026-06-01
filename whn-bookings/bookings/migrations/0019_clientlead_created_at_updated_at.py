from django.db import migrations, models


def forwards_copy_timestamps(apps, schema_editor):
    ClientLead = apps.get_model('bookings', 'ClientLead')
    for lead in ClientLead.objects.all().iterator():
        created_at = getattr(lead, 'created_date', None)
        updated_at = getattr(lead, 'last_updated', None)

        if created_at is None:
            created_at = updated_at
        if created_at is None:
            continue
        if updated_at is None:
            updated_at = created_at
        elif abs((updated_at - created_at).total_seconds()) <= 5:
            updated_at = created_at

        ClientLead.objects.filter(pk=lead.pk).update(
            created_at=created_at,
            updated_at=updated_at,
        )


def backwards_copy_timestamps(apps, schema_editor):
    ClientLead = apps.get_model('bookings', 'ClientLead')
    for lead in ClientLead.objects.all().iterator():
        created_at = getattr(lead, 'created_at', None)
        updated_at = getattr(lead, 'updated_at', None)

        if created_at is None:
            continue
        if updated_at is None:
            updated_at = created_at

        ClientLead.objects.filter(pk=lead.pk).update(
            created_date=created_at,
            last_updated=updated_at,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0018_employeeleadactivity'),
    ]

    operations = [
        migrations.AddField(
            model_name='clientlead',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='clientlead',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, blank=True, null=True),
        ),
        migrations.RunPython(forwards_copy_timestamps, backwards_copy_timestamps),
    ]
