"""Signed user assertions, unit level with an injectable clock (design §6 rows 5-14)."""

from __future__ import annotations

import base64
import json
import time
import unittest

import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from _security_fixtures import AUDIENCE, DELETE, make_world, new_jti
from shared_mcp_server.auth.assertions import AssertionVerifier, VerifiedUser
from shared_mcp_server.auth.replay import ReplayCache
from shared_mcp_server.errors import McpSecurityError

TOOL = "testapp_echo_context"


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


class AssertionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.world = make_world()
        self.app = self.world.testapp
        self.now = float(int(time.time()))
        self.cache = ReplayCache(clock=lambda: self.now)
        self.verifier = AssertionVerifier(
            self.world.registry.apps.values(),
            audience=AUDIENCE,
            max_lifetime_seconds=60,
            clock_skew_seconds=5,
            replay_cache=self.cache,
            clock=lambda: self.now,
        )

    def verify(self, token: str | list[str], action: str = "tools/list", tool: str | None = None, **kwargs) -> VerifiedUser:
        values = token if isinstance(token, list) else [token]
        return self.verifier.verify(values, app_id=kwargs.pop("app_id", "testapp"), action=action, tool=tool, **kwargs)

    def reason(self, token: str | list[str], action: str = "tools/list", tool: str | None = None, **kwargs) -> str:
        with self.assertRaises(McpSecurityError) as caught:
            self.verify(token, action, tool, **kwargs)
        self.assertEqual(caught.exception.code, "UNAUTHENTICATED")
        return caught.exception.reason

    def times(self, iat_offset: float = 0, lifetime: float = 30) -> dict:
        return {"iat": self.now + iat_offset, "exp": self.now + iat_offset + lifetime}


class ValidAssertionTests(AssertionTestCase):
    def test_list_assertion(self) -> None:
        token = self.app.assertion(sub="usr-42", tid="tenant-002", role="CLINIC_OWNER", cid="cid-abcdef12")
        user = self.verify(token)
        self.assertEqual(
            (user.app_id, user.user_id, user.tenant_id, user.role, user.correlation_id, user.action, user.tool),
            ("testapp", "usr-42", "tenant-002", "CLINIC_OWNER", "cid-abcdef12", "tools/list", None),
        )
        self.assertEqual(user.raw, token)
        self.assertNotIn(token, repr(user))

    def test_call_assertion_bound_to_tool(self) -> None:
        user = self.verify(self.app.assertion("tools/call", TOOL), "tools/call", TOOL)
        self.assertEqual(user.tool, TOOL)

    def test_permission_claims_are_ignored(self) -> None:
        user = self.verify(self.app.assertion(permissions=["*"], perms=["inventory:manage"], is_admin=True))
        self.assertFalse(hasattr(user, "permissions"))
        self.assertEqual(user.role, "NURSE_STAFF")

    def test_clock_skew_tolerance_is_five_seconds(self) -> None:
        self.verify(self.app.assertion(iat=self.now - 33, exp=self.now - 3))  # expired 3 s ago: within skew
        self.verify(self.app.assertion(iat=self.now + 4, exp=self.now + 30))  # issued 4 s in the future
        self.verify(self.app.assertion(nbf=self.now + 4, **self.times()))


class MalformedAssertionTests(AssertionTestCase):
    def test_missing_empty_duplicate(self) -> None:
        self.assertEqual(self.reason([]), "MISSING_ASSERTION")
        self.assertEqual(self.reason(""), "MISSING_ASSERTION")
        token = self.app.assertion()
        self.assertEqual(self.reason([token, token]), "BAD_ASSERTION")

    def test_oversized_and_not_a_jwt(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(padding="x" * 4000)), "BAD_ASSERTION")
        for value in ("not-a-jwt", "a.b", "a.b.c.d", "eyJ.eyJ.###", "Bearer x.y.z", "a.b.c"):
            with self.subTest(value=value):
                self.assertEqual(self.reason(value), "BAD_ASSERTION")

    def test_jose_header_rules(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(headers={"typ": "JWT"})), "BAD_ASSERTION")
        self.assertEqual(self.reason(self.app.assertion(headers={"kid": None})), "BAD_ASSERTION")
        for param in ("jku", "x5u", "crit"):
            with self.subTest(param=param):
                self.assertEqual(self.reason(self.app.assertion(headers={param: "https://evil.example"})), "BAD_ASSERTION")
        jwk = {"kty": "OKP", "crv": "Ed25519", "x": "AAAA"}
        self.assertEqual(self.reason(self.app.assertion(headers={"jwk": jwk})), "BAD_ASSERTION")


class SignatureTests(AssertionTestCase):
    def test_signature_by_another_key(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(key=Ed25519PrivateKey.generate())), "BAD_SIGNATURE")

    def test_tampered_payload(self) -> None:
        header, _, signature = self.app.assertion().split(".")
        forged = b64(self.app.claims(role="CLINIC_OWNER"))
        self.assertEqual(self.reason(f"{header}.{forged}.{signature}"), "BAD_SIGNATURE")

    def test_alg_none(self) -> None:
        header = b64({"alg": "none", "typ": "mcp-user+jwt", "kid": self.app.kid})
        for signature in ("", "c2ln"):
            token = f"{header}.{b64(self.app.claims())}.{signature}"
            if signature == "":
                self.assertEqual(self.reason(token), "BAD_ASSERTION")  # not even compact-JWS shaped
            else:
                self.assertEqual(self.reason(token), "BAD_ALGORITHM")

    def test_hs256_keyed_with_the_public_key(self) -> None:
        public_raw = self.app.private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        token = jwt.encode(
            self.app.claims(), public_raw, algorithm="HS256", headers={"typ": "mcp-user+jwt", "kid": self.app.kid}
        )
        self.assertEqual(self.reason(token), "BAD_ALGORITHM")

    def test_rs256_and_es256(self) -> None:
        jose = {"typ": "mcp-user+jwt", "kid": self.app.kid}
        rs = jwt.encode(self.app.claims(), rsa.generate_private_key(65537, 2048), algorithm="RS256", headers=jose)
        es = jwt.encode(self.app.claims(), ec.generate_private_key(ec.SECP256R1()), algorithm="ES256", headers=jose)
        self.assertEqual(self.reason(rs), "BAD_ALGORITHM")
        self.assertEqual(self.reason(es), "BAD_ALGORITHM")

    def test_header_alg_eddsa_but_forged_signature(self) -> None:
        header = b64({"alg": "EdDSA", "typ": "mcp-user+jwt", "kid": self.app.kid})
        self.assertEqual(self.reason(f"{header}.{b64(self.app.claims())}.c2lnbmF0dXJl"), "BAD_SIGNATURE")


class IssuerAndKeyTests(AssertionTestCase):
    def test_wrong_or_missing_issuer(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(iss="unknownapp")), "ISSUER_APP_MISMATCH")
        self.assertEqual(self.reason(self.app.assertion(iss=DELETE)), "WRONG_ISSUER")
        self.assertEqual(self.reason(self.app.assertion(iss=123)), "WRONG_ISSUER")

    def test_assertion_of_another_registered_app(self) -> None:
        # app A's service token (app_id=testapp) + app B's correctly signed assertion
        other = self.world.otherapp.assertion()
        self.assertEqual(self.reason(other, app_id="testapp"), "ISSUER_APP_MISMATCH")
        self.verify(self.world.otherapp.assertion(), app_id="otherapp")  # valid for its own app

    def test_issuer_claims_testapp_but_signed_with_other_apps_key(self) -> None:
        other = self.world.otherapp
        token = self.app.assertion(key=other.private_key, headers={"kid": other.kid})
        self.assertEqual(self.reason(token), "UNKNOWN_KEY")
        token = self.app.assertion(key=other.private_key)  # testapp's kid, other key
        self.assertEqual(self.reason(token), "BAD_SIGNATURE")

    def test_unknown_kid(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(headers={"kid": "kid-unknown"})), "UNKNOWN_KEY")


class ClaimTests(AssertionTestCase):
    def test_audience(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(aud="practicare-backend")), "WRONG_AUDIENCE")
        self.assertEqual(self.reason(self.app.assertion(aud=DELETE)), "WRONG_AUDIENCE")
        self.assertEqual(self.reason(self.app.assertion(aud=[AUDIENCE])), "WRONG_AUDIENCE")

    def test_expiry_and_time_claims(self) -> None:
        self.assertEqual(self.reason(self.app.assertion(**self.times(iat_offset=-100))), "EXPIRED_ASSERTION")
        self.assertEqual(self.reason(self.app.assertion(iat=self.now - 36, exp=self.now - 6)), "EXPIRED_ASSERTION")
        self.assertEqual(self.reason(self.app.assertion(nbf=self.now + 10, **self.times())), "ASSERTION_NOT_YET_VALID")
        self.assertEqual(self.reason(self.app.assertion(**self.times(iat_offset=30))), "IAT_IN_FUTURE")
        self.assertEqual(self.reason(self.app.assertion(**self.times(lifetime=61))), "LIFETIME_TOO_LONG")
        self.assertEqual(self.reason(self.app.assertion(iat=self.now, exp=self.now)), "BAD_ASSERTION")
        self.verify(self.app.assertion(**self.times(lifetime=60)))

    def test_expiry_follows_the_clock(self) -> None:
        token = self.app.assertion(**self.times(lifetime=30))
        self.now += 35
        self.assertEqual(self.reason(token), "EXPIRED_ASSERTION")

    def test_every_required_claim(self) -> None:
        for claim in ("sub", "tid", "role", "act", "cid", "jti", "iat", "exp"):
            with self.subTest(claim=claim):
                self.assertNotEqual(self.reason(self.app.assertion(**{claim: DELETE})), "")
        self.assertEqual(self.reason(self.app.assertion("tools/call", None), "tools/call", TOOL), "BAD_ASSERTION")

    def test_claim_types_and_formats(self) -> None:
        cases = {
            "sub": [42, "", "user@example.com", "x" * 129, "usr 1", ["usr-1"]],
            "tid": [None, 7, "tenant/001", "../tenant"],
            "role": ["nurse_staff", "Nurse", 3, "R"],
            "cid": ["short", "x" * 65, "cid with space"],
            "jti": ["too-short", 12345678901234567890, "j" * 65],
            "iat": ["now", True, None],
            "exp": ["later", False],
            "act": ["tools/delete", "TOOLS/LIST", None],
        }
        for claim, values in cases.items():
            for value in values:
                with self.subTest(claim=claim, value=value):
                    self.reason(self.app.assertion(**{claim: value}))

    def test_action_and_tool_binding(self) -> None:
        self.assertEqual(self.reason(self.app.assertion("tools/list"), "tools/call", TOOL), "ACTION_MISMATCH")
        self.assertEqual(self.reason(self.app.assertion("tools/call", TOOL), "tools/list"), "ACTION_MISMATCH")
        token = self.app.assertion("tools/call", "testapp_get_owner_summary")
        self.assertEqual(self.reason(token, "tools/call", TOOL), "TOOL_MISMATCH")
        self.assertEqual(self.reason(self.app.assertion("tools/list", TOOL)), "BAD_ASSERTION")

    def test_correlation_header_must_match(self) -> None:
        token = self.app.assertion(cid="cid-0123456789")
        self.assertEqual(self.reason(token, correlation_header=["cid-other-value"]), "CORRELATION_MISMATCH")
        self.assertEqual(
            self.reason(self.app.assertion(cid="cid-0123456789"), correlation_header=["cid-0123456789"] * 2),
            "CORRELATION_MISMATCH",
        )
        self.assertEqual(self.verify(token, correlation_header=["cid-0123456789"]).correlation_id, "cid-0123456789")

    def test_failed_verification_does_not_consume_jti(self) -> None:
        jti = new_jti()
        self.assertEqual(self.reason(self.app.assertion(jti=jti, aud="wrong")), "WRONG_AUDIENCE")
        self.assertEqual(self.reason(self.app.assertion(jti=jti, key=Ed25519PrivateKey.generate())), "BAD_SIGNATURE")
        self.verify(self.app.assertion(jti=jti))
        self.assertEqual(self.reason(self.app.assertion(jti=jti)), "REPLAYED")


if __name__ == "__main__":
    unittest.main()
