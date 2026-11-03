"""Development keys: ``python -m notify_hub.keys`` writes a ``.env`` block for a local hub.

In the cluster the VAPID key and the app tokens are generated and sealed by the
Home-Lab-Infra scripts (``make notify-vapid``, ``make notify-token``), so they
never pass through a terminal. This is only for running the hub on a laptop.

Example:
    >>> pem = new_vapid_pem()
    >>> pem.startswith("-----BEGIN PRIVATE KEY-----")
    True
"""

from __future__ import annotations

import json
import secrets
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from notify_hub.auth import digest


def new_vapid_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()


def main(apps: list[str]) -> None:
    pem = new_vapid_pem().replace("\n", "\\n")
    tokens = {app: secrets.token_urlsafe(32) for app in apps or ["my-app"]}
    print(f'NOTIFY_VAPID_PRIVATE_KEY="{pem}"')
    print(f"NOTIFY_APPS='{json.dumps({app: digest(tok) for app, tok in tokens.items()})}'")
    for app, tok in tokens.items():
        print(f"# token for {app} (its NOTIFY_TOKEN): {tok}")


if __name__ == "__main__":
    main(sys.argv[1:])
