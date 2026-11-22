"""Create demo data: products, prices, stock, delivery settings and stations.

    python manage.py seed_demo                   (your own machine)
    python manage.py seed_demo --allow-staging   (the staging server)

It never runs on production settings. It is safe to run twice: everything is created only if it
is missing, and each stock receipt has its own key, so stock is counted once. Demo products are
recognised by their SKUs, which start with DEMO-.

It makes no product photos: those go through the image pipeline, which this command does not touch.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category, PriceTier, Product, Variant
from apps.delivery.models import DeliverySettings, Station
from apps.inventory import services as inventory

# (product name, slug, category slug, [(size, colour, retail price in pesewas, stock)])
PRODUCTS = [
    (
        "Classic white tee",
        "classic-white-tee",
        "clothes",
        [("S", "White", 6500, 12), ("M", "White", 6500, 15), ("L", "White", 6500, 9),
         ("XL", "White", 6500, 0)],
    ),
    (
        "Blue denim jeans",
        "blue-denim-jeans",
        "clothes",
        [("30", "Blue", 14000, 6), ("32", "Blue", 14000, 8), ("34", "Blue", 14000, 1)],
    ),
    (
        "Black hoodie",
        "black-hoodie",
        "clothes",
        [("M", "Black", 18000, 10), ("L", "Black", 18000, 7)],
    ),
    (
        "Ankara print shirt",
        "ankara-print-shirt",
        "clothes",
        [("M", "Orange", 12000, 5), ("L", "Orange", 12000, 5), ("L", "Green", 12000, 3)],
    ),
    (
        "Everyday sneakers",
        "everyday-sneakers",
        "shoes",
        [("41", "White", 25000, 4), ("42", "White", 25000, 4), ("43", "White", 25000, 0)],
    ),
    (
        "Leather sandals",
        "leather-sandals",
        "shoes",
        [("40", "Brown", 9500, 6), ("42", "Brown", 9500, 6)],
    ),
    ("Cotton socks, pack of 3", "cotton-socks-3", "accessories", [("", "Grey", 3000, 40)]),
    (
        "Baseball cap",
        "baseball-cap",
        "accessories",
        [("", "Navy", 4500, 20), ("", "Red", 4500, 20)],
    ),
]
CATEGORIES = {"clothes": "Clothes", "shoes": "Shoes", "accessories": "Accessories"}
# Tamale is left out on purpose: an unlisted station makes an order wait for a delivery quote.
STATIONS = [("Kumasi station", 2500), ("Takoradi station", 3000), ("Cape Coast station", 2000)]


def check_environment(settings_module: str, allow_staging: bool) -> None:
    if settings_module.endswith(".prod"):
        raise CommandError("seed_demo never runs on production settings.")
    if settings_module.endswith(".staging") and not allow_staging:
        raise CommandError("These are staging settings. Add --allow-staging if you mean it.")


def seed() -> list[tuple[int, str, str, str, int, int]]:
    """Create the demo data. Returns (variant id, name, size, colour, price, stock) per variant."""
    categories = {
        slug: Category.objects.get_or_create(slug=slug, defaults={"name": name})[0]
        for slug, name in CATEGORIES.items()
    }
    made = []
    for name, slug, category_slug, variants in PRODUCTS:
        product, _ = Product.objects.get_or_create(
            slug=slug, defaults={"name": name, "category": categories[category_slug]}
        )
        for size, colour, price, stock in variants:
            sku = "-".join(part for part in ("DEMO", slug.upper(), size, colour.upper()) if part)
            variant, _ = Variant.objects.get_or_create(
                sku=sku,
                defaults={"product": product, "size": size, "colour": colour, "is_active": True},
            )
            PriceTier.objects.get_or_create(
                variant=variant, tier="retail", defaults={"price_pesewas": price}
            )
            if stock:
                inventory.receive_stock(variant.pk, stock, idempotency_key=f"seed-demo-{sku}")
            made.append((variant.pk, name, size, colour, price, stock))

    if not DeliverySettings.objects.exists():
        DeliverySettings.objects.create(
            shop_latitude="5.603700",
            shop_longitude="-0.187000",
            minimum_fee_pesewas=1000,
            base_fee_pesewas=500,
            rate_per_km_pesewas=200,
            max_distance_km="30.00",
            road_factor="1.30",
        )
    for station_name, fee in STATIONS:
        Station.objects.get_or_create(name=station_name, defaults={"fee_pesewas": fee})
    return made


class Command(BaseCommand):
    help = "Create demo products, stock, delivery settings and stations. Never on production."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-staging",
            action="store_true",
            help="Allow this on the staging server (it is always refused on production).",
        )

    def handle(self, *args, **options):
        check_environment(str(getattr(settings, "SETTINGS_MODULE", "")), options["allow_staging"])
        with transaction.atomic():
            made = seed()
        self.stdout.write("Demo data is in place. Variant numbers:")
        for variant_id, name, size, colour, price, stock in made:
            label = " ".join(part for part in (name, size, colour) if part)
            money = f"GHS {price / 100:>7.2f}"
            self.stdout.write(f"  {variant_id:>4}  {label:<45} {money}  stock {stock}")
        self.stdout.write("Stations with a fee: " + ", ".join(n for n, _ in STATIONS))
        self.stdout.write("Unlisted on purpose: Tamale (an order there waits for a quote).")
