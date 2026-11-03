import decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Station",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=100)),
                ("name_key", models.CharField(editable=False, max_length=100, unique=True)),
                ("fee_pesewas", models.PositiveBigIntegerField()),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="DeliverySettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("shop_latitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("shop_longitude", models.DecimalField(decimal_places=6, max_digits=9)),
                ("minimum_fee_pesewas", models.PositiveBigIntegerField()),
                ("base_fee_pesewas", models.PositiveBigIntegerField()),
                ("rate_per_km_pesewas", models.PositiveBigIntegerField()),
                ("max_distance_km", models.DecimalField(decimal_places=2, max_digits=6)),
                (
                    "road_factor",
                    models.DecimalField(
                        decimal_places=2, default=decimal.Decimal("1.30"), max_digits=4
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "delivery settings",
            },
        ),
        migrations.AddConstraint(
            model_name="deliverysettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("id", 1)), name="deliverysettings_single_row"
            ),
        ),
        migrations.AddConstraint(
            model_name="deliverysettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("max_distance_km__gt", 0)),
                name="deliverysettings_distance_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="deliverysettings",
            constraint=models.CheckConstraint(
                condition=models.Q(("road_factor__gt", 0)),
                name="deliverysettings_road_factor_positive",
            ),
        ),
    ]
