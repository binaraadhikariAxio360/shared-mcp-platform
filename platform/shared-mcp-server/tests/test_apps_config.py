"""MCP_APPS_FILE loading and validation; startup refuses anything unsafe."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from _security_fixtures import new_service_token, utc
from shared_mcp_server import __main__ as entry_point
from shared_mcp_server.apps_config import load_apps_file, parse_apps
from shared_mcp_server.auth.service_tokens import hash_token
from shared_mcp_server.config import ConfigError

EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "apps.example.json"


def public_pem(key=None) -> str:
    key = key or Ed25519PrivateKey.generate()
    return key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()


def iso(offset: timedelta) -> str:
    return utc(offset).isoformat().replace("+00:00", "Z")


def app_entry(app_id: str = "practicare", token: str | None = None) -> dict:
    return {
        "app_id": app_id,
        "display_name": app_id.title(),
        "client_tokens": [
            {
                "token_id": f"{app_id}-svc-1",
                "sha256": hash_token(token or new_service_token()),
                "not_before": iso(timedelta(days=-1)),
                "not_after": iso(timedelta(days=90)),
            }
        ],
        "assertion_keys": [{"kid": f"{app_id}-key-1", "public_key_pem": public_pem()}],
    }


def document(*apps: dict) -> dict:
    return {"apps": list(apps) or [app_entry()]}


class ParseAppsTests(unittest.TestCase):
    def test_valid_file(self) -> None:
        token = new_service_token()
        apps = parse_apps(json.dumps(document(app_entry(token=token), app_entry("taxsnap"))))
        self.assertEqual([app.app_id for app in apps], ["practicare", "taxsnap"])
        self.assertEqual(apps[0].client_tokens[0].sha256, hash_token(token))
        self.assertEqual(apps[0].assertion_keys[0].kid, "practicare-key-1")

    def test_not_before_is_optional(self) -> None:
        doc = document()
        del doc["apps"][0]["client_tokens"][0]["not_before"]
        self.assertEqual(len(parse_apps(json.dumps(doc))), 1)

    def assert_refused(self, doc_or_text, pattern: str = "") -> None:
        text = doc_or_text if isinstance(doc_or_text, str) else json.dumps(doc_or_text)
        with self.assertRaisesRegex(ConfigError, pattern):
            parse_apps(text)

    def test_structure_errors(self) -> None:
        self.assert_refused("{not json", "not valid JSON")
        self.assert_refused([], "must be an object")
        self.assert_refused({"apps": {}}, "must be a list")
        self.assert_refused({"apps": [], "extra": 1}, "unknown fields")
        for field in ("app_id", "display_name", "client_tokens", "assertion_keys"):
            entry = app_entry()
            del entry[field]
            with self.subTest(missing=field):
                self.assert_refused(document(entry), "missing")
        entry = app_entry()
        entry["client_tokens"][0]["not_afer"] = entry["client_tokens"][0].pop("not_after")
        self.assert_refused(document(entry), "unknown fields")
        for field in ("client_tokens", "assertion_keys"):
            entry = app_entry()
            entry[field] = []
            with self.subTest(empty=field):
                self.assert_refused(document(entry), "non-empty")

    def test_token_validity_rules(self) -> None:
        cases = {
            "in the past": {"not_after": iso(timedelta(seconds=-1))},
            "180 days": {"not_before": iso(timedelta(0)), "not_after": iso(timedelta(days=181))},
            "timezone": {"not_after": utc(timedelta(days=10)).replace(tzinfo=None).isoformat()},
            "ISO 8601": {"not_after": "next tuesday"},
            "not_before must precede": {"not_before": iso(timedelta(days=20)), "not_after": iso(timedelta(days=10))},
        }
        for pattern, change in cases.items():
            entry = app_entry()
            entry["client_tokens"][0].update(change)
            with self.subTest(pattern=pattern):
                self.assert_refused(document(entry), pattern)

    def test_hash_and_id_rules(self) -> None:
        for sha in ("", "ABC", "g" * 64, hash_token(new_service_token()).upper()):
            entry = app_entry()
            entry["client_tokens"][0]["sha256"] = sha
            with self.subTest(sha=sha[:8]):
                self.assert_refused(document(entry), "sha256")
        entry = app_entry()
        entry["client_tokens"][0]["sha256"] = 123
        self.assert_refused(document(entry), "strings")

    def test_raw_token_instead_of_hash_refused(self) -> None:
        entry = app_entry()
        entry["client_tokens"][0]["sha256"] = new_service_token()
        self.assert_refused(document(entry), "sha256")

    def test_duplicates(self) -> None:
        self.assert_refused(document(app_entry(), app_entry()), "duplicate app_id")
        token = new_service_token()
        self.assert_refused(document(app_entry(token=token), app_entry("taxsnap", token=token)), "registered twice")
        entry = app_entry()
        entry["assertion_keys"].append(copy.deepcopy(entry["assertion_keys"][0]))
        self.assert_refused(document(entry), "duplicate kid")

    def test_key_rules(self) -> None:
        rsa_pem = generate_private_key(65537, 2048).public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()
        for pem, pattern in ((rsa_pem, "Ed25519"), ("not a pem", "PEM public key"), ("", "PEM public key")):
            entry = app_entry()
            entry["assertion_keys"][0]["public_key_pem"] = pem
            with self.subTest(pattern=pattern):
                self.assert_refused(document(entry), pattern)

    def test_private_key_material_refused(self) -> None:
        private_pem = Ed25519PrivateKey.generate().private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
        entry = app_entry()
        entry["assertion_keys"][0]["public_key_pem"] = private_pem
        self.assert_refused(document(entry), "private key")

    def test_invalid_app_id(self) -> None:
        self.assert_refused(document(app_entry("Practi-Care")), "app_id")


class LoadAppsFileTests(unittest.TestCase):
    def test_no_file_configured_means_no_apps(self) -> None:
        self.assertEqual(load_apps_file(None), [])
        self.assertEqual(load_apps_file(""), [])

    def test_missing_unreadable_and_oversized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ConfigError, "cannot read"):
                load_apps_file(os.path.join(tmp, "missing.json"))
            big = Path(tmp, "big.json")
            big.write_bytes(b" " * (1024 * 1024 + 1))
            with self.assertRaisesRegex(ConfigError, "larger than 1 MB"):
                load_apps_file(str(big))
            binary = Path(tmp, "bin.json")
            binary.write_bytes(b"\xff\xfe\x00")
            with self.assertRaisesRegex(ConfigError, "UTF-8"):
                load_apps_file(str(binary))
            good = Path(tmp, "apps.json")
            good.write_text(json.dumps(document()), encoding="utf-8")
            self.assertEqual(load_apps_file(str(good))[0].app_id, "practicare")

    def test_example_file_holds_placeholders_only(self) -> None:
        text = EXAMPLE.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"mcpsvc_[A-Za-z0-9_-]{43}", text))  # no real token
        self.assertIsNone(re.search(r"\b[0-9a-f]{64}\b", text))  # no real hash
        self.assertNotIn("BEGIN", text)
        example = json.loads(text)
        self.assertEqual(set(example["apps"][0]), {"app_id", "display_name", "client_tokens", "assertion_keys"})
        with self.assertRaises(ConfigError):  # placeholders can never pass validation by accident
            parse_apps(text)

    def test_entry_point_refuses_invalid_apps_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp, "apps.json")
            bad.write_text("{}", encoding="utf-8")
            with mock.patch.dict(os.environ, {"MCP_APPS_FILE": str(bad)}), mock.patch.object(entry_point.uvicorn, "run") as run:
                with mock.patch("sys.stderr"):
                    self.assertEqual(entry_point.main(), 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
