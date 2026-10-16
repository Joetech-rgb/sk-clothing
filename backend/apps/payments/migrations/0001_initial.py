from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PaystackWebhookEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("dedupe_key", models.CharField(max_length=200, unique=True)),
                ("event_type", models.CharField(max_length=64)),
                ("reference", models.CharField(max_length=100)),
                ("amount", models.BigIntegerField(blank=True, null=True)),
                ("currency", models.CharField(blank=True, max_length=3)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
