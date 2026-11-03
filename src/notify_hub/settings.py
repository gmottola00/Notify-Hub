"""Application settings.

One ``Settings`` object, loaded once. Nothing else reads ``os.environ``.

Apps are identified by their token: ``NOTIFY_APPS`` maps an app name to the
**SHA-256 hex digest** of its token. The digest is not a secret, so it lives in
a ConfigMap in Git; the token itself lives only in the calling app's secret.
Adding an app never means re-sealing the hub's own secret.

Example:
    >>> s = Settings(apps={"alfred": "ab" * 32})
    >>> s.vapid_subject
    'mailto:admin@example.com'
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

# py_vapid's own validator, private but the exact rule applied when signing.
from py_vapid import _check_sub  # type: ignore[attr-defined]
from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment and ``.env`` (prefix ``NOTIFY_``)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="NOTIFY_",
        extra="ignore",
        populate_by_name=True,
    )

    # --- Push ----------------------------------------------------------------
    vapid_private_key: SecretStr | None = None
    """EC P-256 private key, PEM. One key for every app: rotating it invalidates
    every subscription on every phone, which then has to subscribe again."""

    vapid_subject: str = "mailto:admin@example.com"
    """``sub`` claim of the VAPID JWT: ``mailto:name@domain`` or a bare ``https://host``
    (no path). Apple rejects placeholders and localhost, so set a real one in the cluster."""

    apps: dict[str, str] = {}
    """App name → SHA-256 hex digest of its bearer token. JSON in the environment."""

    send_concurrency: int = 10
    """Pushes in flight at once for one notify call."""

    default_ttl: int = 86_400
    """Seconds the push service keeps a notification for a phone that is offline."""

    push_timeout: float = 10.0

    # --- Storage -------------------------------------------------------------
    database_url: str = Field(
        default="sqlite+aiosqlite:///./notify.db",
        validation_alias=AliasChoices("NOTIFY_DATABASE_URL", "DATABASE_URL"),
    )
    """SQLAlchemy URL. Also read from plain ``DATABASE_URL``, the key ``make pg-user`` writes."""

    # --- Logging -------------------------------------------------------------
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    @field_validator("apps")
    @classmethod
    def _digests(cls, value: dict[str, str]) -> dict[str, str]:
        """Each value must look like a SHA-256 hex digest, so a pasted token is caught at boot.

        Example:
            >>> Settings(apps={"alfred": "not-a-digest"})
            Traceback (most recent call last):
            ...
            pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
            ...
        """
        for name, digest in value.items():
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
                raise ValueError(f"NOTIFY_APPS[{name!r}] is not a sha256 hex digest")
        return {name: digest.lower() for name, digest in value.items()}

    @field_validator("vapid_subject")
    @classmethod
    def _subject(cls, value: str) -> str:
        """The same check py_vapid runs on every send, moved to boot: a bad subject
        would otherwise fail every push, silently, as ``failed``.

        Example:
            >>> Settings(vapid_subject="https://alfred.example.com").vapid_subject
            'https://alfred.example.com'
            >>> Settings(vapid_subject="https://github.com/someone")
            Traceback (most recent call last):
            ...
            pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
            ...
        """
        value = value.strip()
        if not _check_sub(value):
            raise ValueError(
                f"NOTIFY_VAPID_SUBJECT={value!r} is rejected by the push library: "
                "use mailto:name@domain or https://host with no path"
            )
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings, constructed once. ``cache_clear()`` in tests."""
    return Settings()


__all__ = ["Settings", "get_settings"]
