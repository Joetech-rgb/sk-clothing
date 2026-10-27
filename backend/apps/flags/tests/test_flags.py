import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.flags import services
from apps.flags.models import DirectWriteError, FeatureFlag, FlagChange
from apps.flags.services import enabled_keys, is_enabled, set_flag, snapshot

pytestmark = pytest.mark.django_db

ACTOR = "user:1"


def changes(key="reviews"):
    return list(FlagChange.objects.filter(flag_key=key))


# --- behaviour --------------------------------------------------------------------------------


def test_unknown_flag_is_off():
    assert is_enabled("never_created") is False
    assert "never_created" not in snapshot()


def test_new_flag_defaults_to_off():
    set_flag("reviews", False, actor=ACTOR)
    assert is_enabled("reviews") is False


def test_flag_can_be_switched_on_and_off():
    set_flag("reviews", True, actor=ACTOR)
    assert is_enabled("reviews") is True
    set_flag("reviews", False, actor=ACTOR)
    assert is_enabled("reviews") is False


def test_set_flag_updates_one_row_and_keeps_description():
    set_flag("reviews", True, actor=ACTOR, description="Product reviews")
    set_flag("reviews", False, actor=ACTOR)
    assert FeatureFlag.objects.count() == 1
    assert FeatureFlag.objects.get().description == "Product reviews"
    set_flag("reviews", False, actor=ACTOR, description="Changed")
    assert FeatureFlag.objects.get().description == "Changed"


def test_one_flag_does_not_affect_another():
    set_flag("reviews", True, actor=ACTOR)
    set_flag("favourites", False, actor=ACTOR)
    assert is_enabled("reviews") and not is_enabled("favourites")


@pytest.mark.parametrize(
    "key", ["", "A", "Reviews", "1reviews", "has space", "has-dash", "x", "a" * 65, "résumé"]
)
def test_badly_formed_keys_are_refused_and_leave_no_trace(key):
    with pytest.raises(ValidationError):
        set_flag(key, True, actor=ACTOR)
    assert FeatureFlag.objects.count() == 0
    assert FlagChange.objects.count() == 0


@pytest.mark.parametrize("key", ["ab", "reviews", "product_video_2", "a" * 64])
def test_well_formed_keys_are_accepted(key):
    assert set_flag(key, True, actor=ACTOR).key == key


# --- audit trail ------------------------------------------------------------------------------


def test_creating_a_flag_is_recorded():
    set_flag("reviews", True, actor="user:7", description="Product reviews")
    (change,) = changes()
    assert change.before is None
    assert change.after == {"enabled": True, "description": "Product reviews"}
    assert change.actor == "user:7"
    assert change.created_at is not None


def test_every_real_change_is_recorded_with_before_and_after_and_who():
    set_flag("reviews", False, actor="user:1")
    set_flag("reviews", True, actor="user:2")
    set_flag("reviews", True, actor="user:3", description="Now with photos")
    set_flag("reviews", False, actor="system")
    rows = changes()
    assert [row.actor for row in rows] == ["user:1", "user:2", "user:3", "system"]
    assert rows[1].before == {"enabled": False, "description": ""}
    assert rows[1].after == {"enabled": True, "description": ""}
    assert rows[2].before["description"] == ""
    assert rows[2].after["description"] == "Now with photos"
    assert rows[3].before["enabled"] is True and rows[3].after["enabled"] is False


def test_setting_the_value_it_already_has_records_nothing():
    set_flag("reviews", True, actor=ACTOR, description="x")
    set_flag("reviews", True, actor=ACTOR, description="x")
    set_flag("reviews", True, actor=ACTOR)
    assert len(changes()) == 1


@pytest.mark.parametrize("actor", ["", "   "])
def test_an_actor_is_required_and_nothing_is_written_without_one(actor):
    with pytest.raises(ValueError):
        set_flag("reviews", True, actor=actor)
    assert FeatureFlag.objects.count() == 0
    assert FlagChange.objects.count() == 0


def test_history_survives_a_flag_being_switched_off():
    set_flag("reviews", True, actor=ACTOR)
    set_flag("reviews", False, actor=ACTOR)
    assert len(changes()) == 2


def test_two_people_creating_the_same_flag_at_once_both_succeed(monkeypatch):
    real = services._set_flag
    calls = []

    def racing(key, enabled, description, actor):
        calls.append(actor)
        if len(calls) == 1:
            real(key, False, None, "user:other")  # the other person got there first
            raise IntegrityError("duplicate key")
        return real(key, enabled, description, actor)

    monkeypatch.setattr(services, "_set_flag", racing)
    set_flag("reviews", True, actor="user:me")
    assert is_enabled("reviews") is True
    assert [row.actor for row in changes()] == ["user:other", "user:me"]


def test_a_second_integrity_error_is_not_swallowed(monkeypatch):
    def broken(*args):
        raise IntegrityError("something else is wrong")

    monkeypatch.setattr(services, "_set_flag", broken)
    with pytest.raises(IntegrityError):
        set_flag("reviews", True, actor=ACTOR)


# --- the audit trail cannot be bypassed -------------------------------------------------------


def test_flags_cannot_be_written_around_set_flag():
    flag = set_flag("reviews", False, actor=ACTOR)
    flag.enabled = True
    with pytest.raises(DirectWriteError):
        flag.save()
    with pytest.raises(DirectWriteError):
        FeatureFlag.objects.create(key="sneaky", enabled=True)
    with pytest.raises(DirectWriteError):
        FeatureFlag.objects.bulk_create([FeatureFlag(key="sneaky2", enabled=True)])
    with pytest.raises(DirectWriteError):
        FeatureFlag.objects.filter(key="reviews").update(enabled=True)
    with pytest.raises(DirectWriteError):
        FeatureFlag.objects.all().update(enabled=True)
    with pytest.raises(DirectWriteError):
        flag.delete()
    with pytest.raises(DirectWriteError):
        FeatureFlag.objects.all().delete()
    assert is_enabled("reviews") is False
    assert list(FeatureFlag.objects.values_list("key", flat=True)) == ["reviews"]
    assert len(changes()) == 1


def test_flag_history_cannot_be_rewritten():
    set_flag("reviews", True, actor=ACTOR)
    change = FlagChange.objects.get()
    change.actor = "someone else"
    with pytest.raises(DirectWriteError):
        change.save()
    with pytest.raises(DirectWriteError):
        change.delete()
    with pytest.raises(DirectWriteError):
        FlagChange.objects.all().update(actor="x")
    with pytest.raises(DirectWriteError):
        FlagChange.objects.all().delete()
    assert FlagChange.objects.get().actor == ACTOR


# --- efficiency -------------------------------------------------------------------------------


def test_is_enabled_is_one_query_whether_the_flag_exists_or_not(django_assert_num_queries):
    set_flag("reviews", True, actor=ACTOR)
    with django_assert_num_queries(1):
        assert is_enabled("reviews") is True
    with django_assert_num_queries(1):
        assert is_enabled("missing") is False


def test_a_snapshot_is_one_query_then_every_check_is_free(django_assert_num_queries):
    for i in range(20):
        set_flag(f"flag_{i:02d}", i % 2 == 0, actor=ACTOR)
    with django_assert_num_queries(1):
        flags = snapshot()
    with django_assert_num_queries(0):
        results = [flags.is_enabled(f"flag_{i:02d}") for i in range(20)]
        assert "flag_00" in flags and "flag_01" not in flags and "missing" not in flags
    assert results == [i % 2 == 0 for i in range(20)]


def test_enabled_keys_is_one_query_and_lists_only_flags_that_are_on(django_assert_num_queries):
    set_flag("a_one", True, actor=ACTOR)
    set_flag("b_two", False, actor=ACTOR)
    set_flag("c_three", True, actor=ACTOR)
    with django_assert_num_queries(1):
        keys = enabled_keys()
    assert keys == frozenset({"a_one", "c_three"})


def test_a_snapshot_never_outlives_its_request():
    set_flag("reviews", True, actor=ACTOR)
    old = snapshot()
    set_flag("reviews", False, actor=ACTOR)  # the kill switch
    assert old.is_enabled("reviews") is True  # a held snapshot is stale by design
    assert snapshot().is_enabled("reviews") is False  # the next request sees the change at once


def test_changing_a_flag_costs_a_bounded_number_of_queries(django_assert_max_num_queries):
    set_flag("reviews", False, actor=ACTOR)
    with django_assert_max_num_queries(6):
        set_flag("reviews", True, actor=ACTOR)


def test_flag_key_lookup_uses_a_unique_index():
    assert FeatureFlag._meta.get_field("key").unique is True


# --- admin ------------------------------------------------------------------------------------


@pytest.fixture
def staff_client(client):
    user = get_user_model().objects.create_superuser("boss", "boss@example.com", "pw-12345-xyz")
    client.force_login(user)
    return client, user


def test_admin_add_is_attributed_to_the_staff_member(staff_client):
    client, user = staff_client
    response = client.post(
        "/admin/flags/featureflag/add/",
        {"key": "reviews", "enabled": "on", "description": "Product reviews"},
    )
    assert response.status_code == 302
    (change,) = changes()
    assert change.actor == f"user:{user.pk}"
    assert change.after == {"enabled": True, "description": "Product reviews"}
    assert is_enabled("reviews")


def test_admin_edit_is_recorded_and_the_key_cannot_be_changed(staff_client):
    client, user = staff_client
    flag = set_flag("reviews", False, actor="system")
    response = client.post(
        f"/admin/flags/featureflag/{flag.pk}/change/",
        {"key": "renamed", "enabled": "on", "description": "now on"},
    )
    assert response.status_code == 302
    assert FeatureFlag.objects.get().key == "reviews"
    assert is_enabled("reviews")
    assert changes()[-1].actor == f"user:{user.pk}"
    assert FlagChange.objects.count() == 2


def test_admin_list_toggle_is_recorded(staff_client):
    client, user = staff_client
    flag = set_flag("reviews", False, actor="system")
    response = client.post(
        "/admin/flags/featureflag/",
        {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": str(flag.pk),
            "form-0-enabled": "on",
            "_save": "Save",
        },
    )
    assert response.status_code == 302
    assert is_enabled("reviews")
    assert changes()[-1].actor == f"user:{user.pk}"


def test_admin_cannot_delete_flags_and_history_is_read_only(staff_client):
    client, _ = staff_client
    flag = set_flag("reviews", True, actor="system")
    assert (
        client.post(f"/admin/flags/featureflag/{flag.pk}/delete/", {"post": "yes"}).status_code
        == 403
    )
    assert FeatureFlag.objects.count() == 1
    assert client.get("/admin/flags/flagchange/add/").status_code == 403
    assert client.get("/admin/flags/flagchange/").status_code == 200
