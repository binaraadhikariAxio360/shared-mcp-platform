"""
PractiCare Security and Cryptographic Authentication Module
Enforces server-issued, cryptographically signed, expiring session tokens (HMAC-SHA256).
Prevents token forgery, tenant spoofing, and privilege escalation.
"""

import os
import hmac
import hashlib
import base64
import json
import time
import logging
import secrets
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("practicare.security")


def _load_secret_key() -> str:
    configured = os.getenv("SESSION_SECRET_KEY", "").strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError("SESSION_SECRET_KEY must contain at least 32 characters.")
        return configured
    if os.getenv("ENVIRONMENT", "development").lower() in {"development", "dev", "test"}:
        logger.warning("SESSION_SECRET_KEY is unset; using an ephemeral development key.")
        return secrets.token_urlsafe(48)
    raise RuntimeError("SESSION_SECRET_KEY is required outside development and test environments.")


# Server-side secret key for signing session tokens. Never sourced from a checked-in default.
SECRET_KEY = _load_secret_key()
TOKEN_PREFIX = "pcsess."
TOKEN_LIFETIME_SECONDS = 86400 * 7  # 7 days


def _b64_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding and padding < 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def create_access_token(user_id: str, tenant_id: str, role: str, lifetime_seconds: int = TOKEN_LIFETIME_SECONDS) -> str:
    """
    Creates a cryptographically signed HMAC-SHA256 session token.
    Format: pcsess.<b64_payload>.<b64_signature>
    """
    now = int(time.time())
    payload = {
        "uid": str(user_id),
        "sub": str(user_id),
        "tid": str(tenant_id),
        "tenant_id": str(tenant_id),
        "role": str(role),
        "iat": now,
        "exp": now + lifetime_seconds,
        "iss": "practicare-auth",
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_payload = _b64_encode(payload_json)

    signature = hmac.new(SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).digest()
    b64_sig = _b64_encode(signature)

    return f"{TOKEN_PREFIX}{b64_payload}.{b64_sig}"


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a session token's cryptographic signature, format, and expiration.
    Returns payload dict if valid, or None if invalid/expired/tampered.
    """
    if not token or not isinstance(token, str):
        return None

    clean_token = token.strip()
    if clean_token.startswith("Bearer "):
        clean_token = clean_token[7:].strip()

    # 1. Cryptographically signed tokens (pcsess.<b64_payload>.<b64_sig>)
    if clean_token.startswith(TOKEN_PREFIX):
        raw = clean_token[len(TOKEN_PREFIX):]
        parts = raw.split(".")
        if len(parts) != 2:
            return None

        b64_payload, b64_sig = parts[0], parts[1]

        # Verify HMAC signature in constant time
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), b64_payload.encode("utf-8"), hashlib.sha256).digest()
        try:
            provided_sig = _b64_decode(b64_sig)
            if not hmac.compare_digest(expected_sig, provided_sig):
                logger.warning("Token verification failed: HMAC signature mismatch")
                return None
        except Exception as e:
            logger.warning(f"Signature decode failure: {e}")
            return None

        # Verify payload and expiration
        try:
            payload_bytes = _b64_decode(b64_payload)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            logger.warning(f"Payload decode failure: {e}")
            return None

        now = int(time.time())
        if payload.get("exp") and payload["exp"] < now:
            logger.warning("Token verification failed: Token expired")
            return None

        return payload

    return None
