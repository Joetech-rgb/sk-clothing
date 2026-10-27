from django.core.validators import RegexValidator
from django.db import models

flag_key_validator = RegexValidator(
    r"^[a-z][a-z0-9_]{1,63}$",
    "Use a-z, 0-9 and _ only, starting with a letter (2 to 64).",
)


class DirectWriteError(RuntimeError):
    """Raised when code writes a flag or its history without going through services.set_flag()."""


class FlagQuerySet(models.QuerySet):
    """Blocks bulk writes, which would change flags without leaving an audit row."""

    def update(self, **kwargs):  # type: ignore[override]
        raise DirectWriteError("use services.set_flag() so the change is recorded")

    def delete(self):  # type: ignore[override]
        raise DirectWriteError("flags are never deleted; switch them off")

    def bulk_create(self, *args, **kwargs):  # type: ignore[override]
        raise DirectWriteError("use services.set_flag() so the change is recorded")


class FeatureFlag(models.Model):
    """A switch that turns an unfinished feature on or off without a deploy.

    A flag that does not exist counts as off, so new code can ship dark. Change flags only with
    services.set_flag(): it records who, what and when. Saving directly is refused.
    """

    key = models.CharField(max_length=64, unique=True, validators=[flag_key_validator])
    enabled = models.BooleanField(default=False)
    description = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FlagQuerySet.as_manager()

    class Meta:
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key}: {'on' if self.enabled else 'off'}"

    def save(self, *args, audited: bool = False, **kwargs):
        if not audited:
            raise DirectWriteError("use services.set_flag() so the change is recorded")
        self.full_clean(exclude=["updated_at"], validate_unique=False)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise DirectWriteError("flags are never deleted; switch them off")


class FlagChangeQuerySet(models.QuerySet):
    def update(self, **kwargs):  # type: ignore[override]
        raise DirectWriteError("flag history cannot be changed")

    def delete(self):  # type: ignore[override]
        raise DirectWriteError("flag history cannot be deleted")


class FlagChange(models.Model):
    """Append-only history: one row per real change, written by services.set_flag()."""

    flag_key = models.CharField(max_length=64, db_index=True)
    before = models.JSONField(null=True, blank=True)  # null when the flag was just created
    after = models.JSONField()  # {"enabled": bool, "description": str}
    actor = models.CharField(max_length=64)  # e.g. "user:12", "system"
    created_at = models.DateTimeField(auto_now_add=True)

    objects = FlagChangeQuerySet.as_manager()

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.flag_key} by {self.actor}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise DirectWriteError("flag history cannot be changed")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise DirectWriteError("flag history cannot be deleted")
