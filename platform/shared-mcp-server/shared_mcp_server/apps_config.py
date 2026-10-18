"""Loads application registrations from the JSON file named by `MCP_APPS_FILE`.

The file holds verification material only (service-token SHA-256 hashes and Ed25519 public
keys), never secrets. It is still kept out of Git (`secrets/` is git-ignored); the committed
`config/apps.example.json` shows the structure with placeholders. Any problem stops startup.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from .config import ConfigError
from .registry import AppRegistration, AssertionKey, RegistryError, ServiceCredential, build_registry

MAX_FILE_BYTES = 1024 * 1024
MAX_TOKEN_VALIDITY = timedelta(days=180)

_APP_FIELDS = {"app_id", "display_name", "client_tokens", "assertion_keys"}
_TOKEN_FIELDS = {"token_id", "sha256", "not_before", "not_after"}
_KEY_FIELDS = {"kid", "public_key_pem"}


def _fields(where: str, value: Any, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be an object")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(f"{where} has unknown fields {unknown}")
    missing = sorted(required - set(value))
    if missing:
        raise ConfigError(f"{where} is missing {missing}")
    return value


def _timestamp(where: str, value: Any) -> datetime:
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ConfigError(f"{where} is not a valid ISO 8601 timestamp") from None
    if parsed.tzinfo is None:
        raise ConfigError(f"{where} needs a timezone (for example 'Z')")
    return parsed


def _token(where: str, raw: Any, now: datetime) -> ServiceCredential:
    entry = _fields(where, raw, _TOKEN_FIELDS, {"token_id", "sha256", "not_after"})
    if not isinstance(entry["token_id"], str) or not isinstance(entry["sha256"], str):
        raise ConfigError(f"{where}: token_id and sha256 must be strings")
    not_after = _timestamp(f"{where}.not_after", entry["not_after"])
    not_before = _timestamp(f"{where}.not_before", entry["not_before"]) if "not_before" in entry else None
    if not_after <= now:
        raise ConfigError(f"{where}.not_after is in the past")
    if not_after - (not_before or now) > MAX_TOKEN_VALIDITY:
        raise ConfigError(f"{where}: validity may not exceed {MAX_TOKEN_VALIDITY.days} days")
    return ServiceCredential(
        token_id=entry["token_id"], sha256=entry["sha256"], not_before=not_before, not_after=not_after
    )


def _key(where: str, raw: Any) -> AssertionKey:
    entry = _fields(where, raw, _KEY_FIELDS, _KEY_FIELDS)
    pem = entry["public_key_pem"]
    if not isinstance(entry["kid"], str) or not isinstance(pem, str):
        raise ConfigError(f"{where}: kid and public_key_pem must be strings")
    try:
        key = load_pem_public_key(pem.encode("ascii"))
    except (ValueError, UnicodeEncodeError, TypeError):
        raise ConfigError(f"{where}.public_key_pem is not a PEM public key") from None
    if not isinstance(key, Ed25519PublicKey):
        raise ConfigError(f"{where}.public_key_pem must be an Ed25519 public key")
    return AssertionKey(kid=entry["kid"], public_key=key)


def parse_apps(text: str, now: datetime | None = None) -> list[AppRegistration]:
    now = now or datetime.now(timezone.utc)
    if "PRIVATE KEY" in text:
        raise ConfigError("the apps file must not contain private key material")
    try:
        document = json.loads(text)
    except ValueError:
        raise ConfigError("the apps file is not valid JSON") from None
    document = _fields("apps file", document, {"apps"}, {"apps"})
    if not isinstance(document["apps"], list):
        raise ConfigError("'apps' must be a list")

    apps: list[AppRegistration] = []
    for index, raw_app in enumerate(document["apps"]):
        where = f"apps[{index}]"
        entry = _fields(where, raw_app, _APP_FIELDS, _APP_FIELDS)
        if not isinstance(entry["app_id"], str) or not isinstance(entry["display_name"], str):
            raise ConfigError(f"{where}: app_id and display_name must be strings")
        if not isinstance(entry["client_tokens"], list) or not entry["client_tokens"]:
            raise ConfigError(f"{where}.client_tokens must be a non-empty list")
        if not isinstance(entry["assertion_keys"], list) or not entry["assertion_keys"]:
            raise ConfigError(f"{where}.assertion_keys must be a non-empty list")
        app = AppRegistration(
            app_id=entry["app_id"],
            display_name=entry["display_name"],
            client_tokens=tuple(
                _token(f"{where}.client_tokens[{i}]", raw, now) for i, raw in enumerate(entry["client_tokens"])
            ),
            assertion_keys=tuple(
                _key(f"{where}.assertion_keys[{i}]", raw) for i, raw in enumerate(entry["assertion_keys"])
            ),
        )
        apps.append(app)
    try:
        build_registry(apps)  # ids, hash format, duplicates within and across apps
    except RegistryError as exc:
        raise ConfigError(str(exc)) from None
    return apps


def load_apps_file(path: str | None, now: datetime | None = None) -> list[AppRegistration]:
    """No path configured -> no apps, so every /mcp request is refused (401)."""
    if not path:
        return []
    file = Path(path)
    try:
        if file.stat().st_size > MAX_FILE_BYTES:
            raise ConfigError("the apps file is larger than 1 MB")
        text = file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read MCP_APPS_FILE: {exc.strerror}") from None
    except UnicodeDecodeError:
        raise ConfigError("the apps file is not UTF-8") from None
    return parse_apps(text, now)
