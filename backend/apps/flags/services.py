"""Feature flag services. Other apps call these, never the flag models directly."""

from collections.abc import Iterable

from django.db import IntegrityError, transaction

from .models import FeatureFlag, FlagChange


class FlagSnapshot:
    """Every flag that is on, loaded once. Checking it costs no further queries.

    Build one per request or task and reuse it. It is not shared between requests, so a flag
    switched off is seen by the very next request.
    """

    __slots__ = ("_on",)

    def __init__(self, enabled_keys: Iterable[str]) -> None:
        self._on = frozenset(enabled_keys)

    @classmethod
    def load(cls) -> "FlagSnapshot":
        return cls(FeatureFlag.objects.filter(enabled=True).values_list("key", flat=True))

    def is_enabled(self, key: str) -> bool:
        return key in self._on

    def __contains__(self, key: object) -> bool:
        return key in self._on

    @property
    def enabled_keys(self) -> frozenset[str]:
        return self._on


def is_enabled(key: str) -> bool:
    """True only if the flag exists and is on. Unknown flags are off. One indexed query.

    Checking several flags in one request? Use snapshot() instead: one query for all of them.
    """
    return FeatureFlag.objects.filter(key=key, enabled=True).exists()


def snapshot() -> FlagSnapshot:
    return FlagSnapshot.load()


def enabled_keys() -> frozenset[str]:
    return FlagSnapshot.load().enabled_keys


def _state(flag: FeatureFlag) -> dict:
    return {"enabled": flag.enabled, "description": flag.description}


def _set_flag(key: str, enabled: bool, description: str | None, actor: str) -> FeatureFlag:
    with transaction.atomic():
        flag = FeatureFlag.objects.select_for_update().filter(key=key).first()
        before = None if flag is None else _state(flag)
        if flag is None:
            flag = FeatureFlag(key=key)
        flag.enabled = enabled
        if description is not None:
            flag.description = description
        after = _state(flag)
        if before == after:
            return flag  # nothing changed, so nothing to record
        flag.save(audited=True)
        FlagChange.objects.create(flag_key=key, before=before, after=after, actor=actor)
    return flag


def set_flag(key: str, enabled: bool, *, actor: str, description: str | None = None) -> FeatureFlag:
    """Create the flag if needed and set it, recording who changed what. The only write path.

    `actor` says who is responsible, e.g. "user:12" or "system". Raises ValidationError for a
    badly formed key (nothing is written). Setting the value a flag already has records nothing.
    """
    if not actor or not actor.strip():
        raise ValueError("an actor is required so the change can be attributed")
    try:
        return _set_flag(key, enabled, description, actor)
    except IntegrityError:
        # Two people created the same new flag at the same moment. The other one won, so the
        # flag exists now and a second attempt updates it.
        return _set_flag(key, enabled, description, actor)
