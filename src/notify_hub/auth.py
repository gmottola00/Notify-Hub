"""Bearer token → app name.

The hub stores only SHA-256 digests (``NOTIFY_APPS``), compared in constant time.
Tokens are random and long, so a plain hash is enough: there is nothing to
brute-force the way there would be with a password.

Example:
    >>> len(digest("s3cret")), digest("s3cret") == digest("s3cret")
    (64, True)
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer(auto_error=False)


def digest(token: str) -> str:
    """SHA-256 hex of a token, the form ``NOTIFY_APPS`` stores."""
    return hashlib.sha256(token.encode()).hexdigest()


def resolve(token: str, apps: dict[str, str]) -> str | None:
    """The app whose digest matches ``token``, or None.

    Example:
        >>> resolve("t0k", {"alfred": digest("t0k"), "jarvis": digest("other")})
        'alfred'
        >>> resolve("nope", {"alfred": digest("t0k")}) is None
        True
    """
    candidate = digest(token)
    found = None
    for name, expected in apps.items():  # no early exit: same time whatever matches
        if hmac.compare_digest(candidate, expected):
            found = name
    return found


async def current_app(request: Request, creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    """FastAPI dependency: the calling app, or 401."""
    apps: dict[str, str] = request.app.state.settings.apps
    app = resolve(creds.credentials, apps) if creds is not None else None
    if app is None:
        raise HTTPException(status_code=401, detail="invalid or missing token", headers={"WWW-Authenticate": "Bearer"})
    return app


__all__ = ["current_app", "digest", "resolve"]
