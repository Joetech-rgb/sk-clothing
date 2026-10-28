"""The user model. It must exist before any real database does: changing AUTH_USER_MODEL later
means rewriting migrations and live data.

Customers log in with a phone number (a one-time code), an email, or Google. Staff log in with
email and password. So phone and email are both optional, but at least one is required, and each
is unique when present. Email is stored in lower case so "A@x.com" and "a@x.com" are one person.
Phone numbers are stored as E.164 (+233...), normalised by the manager.
"""

from typing import Any

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from .phone import normalise_ghana_phone


class UserManager(BaseUserManager):
    use_in_migrations = False

    def _create(
        self,
        email: str | None,
        phone: str | None,
        password: str | None,
        **extra: Any,
    ) -> "User":
        email = email.strip().lower() if email else None
        phone = normalise_ghana_phone(phone) if phone else None
        if not email and not phone:
            raise ValueError("a user needs an email or a phone number")
        user = self.model(email=email, phone=phone, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str | None = None,
        phone: str | None = None,
        password: str | None = None,
        **extra: Any,
    ) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, phone, password, **extra)

    def create_superuser(
        self, email: str, password: str | None = None, **extra: Any
    ) -> "User":
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("a superuser must have is_staff and is_superuser set")
        return self._create(email, extra.pop("phone", None), password, **extra)

    def get_by_natural_key(self, username: str) -> "User":
        """Log in by email, ignoring case and stray spaces."""
        return self.get(email=username.strip().lower())


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=254, unique=True, null=True, blank=True)  # noqa: DJ001
    phone = models.CharField(max_length=16, unique=True, null=True, blank=True)  # noqa: DJ001
    full_name = models.CharField(max_length=150, blank=True)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(phone__isnull=False) | models.Q(email__isnull=False),
                name="user_has_phone_or_email",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.email:
            self.email = self.email.strip().lower()
        else:
            self.email = None  # never an empty string: empty strings would collide as unique
        self.phone = normalise_ghana_phone(self.phone) if self.phone else None
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email or self.phone or f"user {self.pk}"


class LoginCode(models.Model):
    """One issued login code. Only the HMAC of the code is stored, never the code itself.

    The database, not application code, guarantees the rules that must hold under concurrent
    requests: a number has at most one live code at a time (the partial unique constraint), and
    the wrong-guess counter and the single-use flag are changed only while the row is locked.
    """

    phone = models.CharField(max_length=16)  # E.164
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=False)
    superseded = models.BooleanField(default=False)  # retired because a newer code was issued
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["phone", "created_at"], name="logincode_phone_created")]
        constraints = [
            models.UniqueConstraint(
                fields=["phone"],
                condition=models.Q(consumed=False, superseded=False),
                name="logincode_one_live_code_per_phone",
            )
        ]

    def __str__(self) -> str:  # never include the number or the hash
        return f"login code {self.pk}"


class SmsDailyCount(models.Model):
    """Login SMS sent per day, across the whole site. The daily spend cap is enforced here, in
    the database, because a cache can be evicted and a cap that resets is not a cap."""

    day = models.DateField(unique=True)  # UTC date (Africa/Accra has no daylight saving)
    count = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"{self.day}: {self.count}"
