import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.catalog.management.commands.seed_demo import check_environment
from apps.catalog.models import PriceTier, Variant
from apps.delivery.models import DeliverySettings, Station


@pytest.mark.django_db
def test_seed_demo_creates_the_demo_shop():
    call_command("seed_demo")
    assert Variant.objects.filter(sku__startswith="DEMO-").count() == 20
    assert PriceTier.objects.filter(variant__sku__startswith="DEMO-", tier="retail").count() == 20
    assert Station.objects.count() == 3
    assert not Station.objects.filter(name__icontains="tamale").exists()
    assert DeliverySettings.objects.count() == 1


@pytest.mark.django_db
def test_running_it_twice_changes_nothing():
    call_command("seed_demo")
    call_command("seed_demo")
    assert Variant.objects.filter(sku__startswith="DEMO-").count() == 20
    assert PriceTier.objects.filter(variant__sku__startswith="DEMO-").count() == 20
    assert Station.objects.count() == 3
    assert DeliverySettings.objects.count() == 1


def test_it_is_always_refused_on_production():
    with pytest.raises(CommandError):
        check_environment("config.settings.prod", allow_staging=False)
    with pytest.raises(CommandError):
        check_environment("config.settings.prod", allow_staging=True)


def test_staging_needs_the_flag():
    with pytest.raises(CommandError):
        check_environment("config.settings.staging", allow_staging=False)
    check_environment("config.settings.staging", allow_staging=True)


def test_local_settings_need_no_flag():
    check_environment("config.settings.local", allow_staging=False)
