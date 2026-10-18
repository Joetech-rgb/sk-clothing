import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

# Each statement is its own list item so Django never has to split `$$` quoted function bodies.
FORBID_CHANGES = [
    """
    CREATE FUNCTION inventory_forbid_stockmovement_change() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'stock movements are append-only';
    END;
    $$ LANGUAGE plpgsql
    """,
    """
    CREATE TRIGGER stockmovement_append_only
    BEFORE UPDATE OR DELETE ON inventory_stockmovement
    FOR EACH ROW EXECUTE FUNCTION inventory_forbid_stockmovement_change()
    """,
]

ALLOW_CHANGES = [
    "DROP TRIGGER stockmovement_append_only ON inventory_stockmovement",
    "DROP FUNCTION inventory_forbid_stockmovement_change()",
]


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Batch",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("variant_id", models.BigIntegerField()),
                ("quantity_received", models.PositiveIntegerField()),
                ("quantity_remaining", models.PositiveIntegerField()),
                ("unit_cost_pesewas", models.PositiveBigIntegerField(blank=True, null=True)),
                ("received_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("idempotency_key", models.CharField(max_length=100, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name="StockLevel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("variant_id", models.BigIntegerField(unique=True)),
                ("on_hand", models.PositiveIntegerField(default=0)),
                ("reserved", models.PositiveIntegerField(default=0)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="Reservation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("variant_id", models.BigIntegerField()),
                ("quantity", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("confirmed", "Confirmed"),
                            ("released", "Released"),
                            ("expired", "Expired"),
                        ],
                        default="active",
                        max_length=16,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=100, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("variant_id", models.BigIntegerField()),
                (
                    "kind",
                    models.CharField(
                        choices=[("receipt", "Receipt"), ("sale", "Sale")], max_length=16
                    ),
                ),
                ("quantity", models.IntegerField()),
                ("idempotency_key", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movements",
                        to="inventory.batch",
                    ),
                ),
                (
                    "reservation",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movements",
                        to="inventory.reservation",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="batch",
            index=models.Index(fields=["variant_id", "received_at", "id"], name="batch_fifo"),
        ),
        migrations.AddConstraint(
            model_name="batch",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity_remaining__lte", models.F("quantity_received"))),
                name="batch_remaining_within_received",
            ),
        ),
        migrations.AddConstraint(
            model_name="batch",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity_received__gt", 0)), name="batch_received_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="stocklevel",
            constraint=models.CheckConstraint(
                condition=models.Q(("reserved__lte", models.F("on_hand"))),
                name="stocklevel_reserved_within_on_hand",
            ),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(
                fields=["status", "expires_at"], name="reservation_status_expiry"
            ),
        ),
        migrations.AddIndex(
            model_name="reservation",
            index=models.Index(
                fields=["variant_id", "status"], name="reservation_variant_status"
            ),
        ),
        migrations.AddConstraint(
            model_name="reservation",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity__gt", 0)), name="reservation_quantity_positive"
            ),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["variant_id"], name="movement_variant"),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantity", 0), _negated=True), name="movement_not_zero"
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                fields=("idempotency_key", "batch"), name="movement_once_per_key_batch"
            ),
        ),
        migrations.RunSQL(sql=FORBID_CHANGES, reverse_sql=ALLOW_CHANGES),
    ]
