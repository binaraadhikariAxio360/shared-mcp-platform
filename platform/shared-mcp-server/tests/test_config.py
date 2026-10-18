from __future__ import annotations

import unittest

from shared_mcp_server.config import ConfigError, Settings, load_settings


class ConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        settings = load_settings({})
        self.assertEqual(settings, Settings())
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8100)
        self.assertEqual(settings.protocol_version, "2025-11-25")
        self.assertEqual(settings.mcp_path, "/mcp")
        self.assertEqual(settings.max_request_body_bytes, 262144)
        self.assertIsNone(settings.apps_file)
        self.assertEqual(settings.assertion_audience, "shared-mcp-server")
        self.assertEqual((settings.assertion_max_lifetime_seconds, settings.clock_skew_seconds), (60, 5))
        self.assertEqual(settings.replay_cache_max_entries, 50000)

    def test_security_overrides(self) -> None:
        settings = load_settings(
            {
                "MCP_APPS_FILE": " secrets/apps.json ",
                "MCP_ASSERTION_AUDIENCE": "shared-mcp-dev",
                "MCP_ASSERTION_MAX_LIFETIME_SECONDS": "30",
                "MCP_CLOCK_SKEW_SECONDS": "2",
                "MCP_REPLAY_CACHE_MAX_ENTRIES": "1000",
            }
        )
        self.assertEqual(settings.apps_file, "secrets/apps.json")
        self.assertEqual(settings.assertion_audience, "shared-mcp-dev")
        self.assertEqual((settings.assertion_max_lifetime_seconds, settings.clock_skew_seconds), (30, 2))
        self.assertEqual(settings.replay_cache_max_entries, 1000)
        self.assertIsNone(load_settings({"MCP_APPS_FILE": "  "}).apps_file)

    def test_approved_security_limits_enforced(self) -> None:
        cases = {
            "MCP_ASSERTION_MAX_LIFETIME_SECONDS": ["61", "300", "0"],
            "MCP_CLOCK_SKEW_SECONDS": ["6", "30", "-1"],
            "MCP_ASSERTION_AUDIENCE": ["", "has space", "a" * 129],
            "MCP_REPLAY_CACHE_MAX_ENTRIES": ["10", "5000000"],
        }
        for name, values in cases.items():
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(ConfigError):
                    load_settings({name: value})

    def test_env_overrides(self) -> None:
        settings = load_settings(
            {
                "MCP_SERVER_HOST": "::1",
                "MCP_SERVER_PORT": "9100",
                "MCP_SERVER_PATH": "/mcp/v1",
                "MCP_MAX_REQUEST_BODY_BYTES": "65536",
                "MCP_LOG_LEVEL": "debug",
            }
        )
        self.assertEqual((settings.host, settings.port, settings.mcp_path), ("::1", 9100, "/mcp/v1"))
        self.assertEqual((settings.max_request_body_bytes, settings.log_level), (65536, "DEBUG"))

    def test_loopback_hosts_accepted(self) -> None:
        for host in ("127.0.0.1", "::1", "localhost"):
            self.assertEqual(load_settings({"MCP_SERVER_HOST": host}).host, host)

    def test_non_loopback_hosts_refused(self) -> None:
        for host in ("0.0.0.0", "::", "192.168.1.10", "10.0.0.5", "shared-mcp-server", "example.com", ""):
            with self.subTest(host=host), self.assertRaisesRegex(ConfigError, "loopback"):
                load_settings({"MCP_SERVER_HOST": host})

    def test_protocol_version_must_be_supported_handshake_version(self) -> None:
        self.assertEqual(load_settings({"MCP_PROTOCOL_VERSION": "2025-06-18"}).protocol_version, "2025-06-18")
        for version in ("2026-07-28", "2099-01-01", "latest", ""):
            with self.subTest(version=version), self.assertRaisesRegex(ConfigError, "MCP_PROTOCOL_VERSION"):
                load_settings({"MCP_PROTOCOL_VERSION": version})

    def test_invalid_values_refused(self) -> None:
        cases = {
            "MCP_SERVER_PORT": ["abc", "70000", "-1"],
            "MCP_SERVER_PATH": ["mcp", "/", "/healthz", "/readyz"],
            "MCP_MAX_REQUEST_BODY_BYTES": ["10", "999999999", "x"],
            "MCP_LOG_LEVEL": ["VERBOSE"],
        }
        for name, values in cases.items():
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(ConfigError):
                    load_settings({name: value})

    def test_settings_are_immutable(self) -> None:
        with self.assertRaises(AttributeError):
            Settings().host = "0.0.0.0"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
