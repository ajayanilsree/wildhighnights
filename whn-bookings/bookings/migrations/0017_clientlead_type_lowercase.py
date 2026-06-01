from django.db import migrations, models


def migrate_type_to_lowercase(apps, schema_editor):
    ClientLead = apps.get_model("bookings", "ClientLead")
    ClientLead.objects.filter(type="Lead").update(type="lead")
    ClientLead.objects.filter(type="Sale").update(type="sale")


def migrate_type_to_titlecase(apps, schema_editor):
    ClientLead = apps.get_model("bookings", "ClientLead")
    ClientLead.objects.filter(type="lead").update(type="Lead")
    ClientLead.objects.filter(type="sale").update(type="Sale")


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0016_booking_created_by_employee_clientlead"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clientlead",
            name="type",
            field=models.CharField(
                choices=[("sale", "Sale"), ("lead", "Lead")],
                default="lead",
                max_length=10,
            ),
        ),
        migrations.RunPython(migrate_type_to_lowercase, migrate_type_to_titlecase),
    ]
