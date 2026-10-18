from __future__ import annotations

import unittest
from dataclasses import replace

from shared_mcp_server.adapters.base import AdapterError, AppAdapter, CallContext
from shared_mcp_server.registry import AppRegistration, RegistryError, ToolManifest, build_registry

PRACTICARE = AppRegistration(app_id="practicare", display_name="PractiCare")
TAXSNAP = AppRegistration(app_id="taxsnap", display_name="TaxSnap")
OBJECT_SCHEMA = {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1}}, "additionalProperties": False}


def tool(**overrides) -> ToolManifest:
    base = ToolManifest(
        name="practicare_list_tasks",
        app_id="practicare",
        description="List visible tasks",
        input_schema=OBJECT_SCHEMA,
        allowed_roles=frozenset({"CLINIC_OWNER", "NURSE_STAFF"}),
    )
    return replace(base, **overrides)


class RegistryTests(unittest.TestCase):
    def test_empty_registry_is_valid(self) -> None:
        registry = build_registry()
        self.assertEqual(len(registry.apps), 0)
        self.assertEqual(len(registry.tools), 0)

    def test_valid_registry(self) -> None:
        registry = build_registry(
            [PRACTICARE, TAXSNAP],
            [tool(), tool(name="practicare_get_inventory_status", output_schema={"type": "object"})],
        )
        self.assertEqual(set(registry.apps), {"practicare", "taxsnap"})
        self.assertEqual(len(registry.tools_for_app("practicare")), 2)
        self.assertEqual(registry.tools_for_app("taxsnap"), [])

    def test_registry_is_read_only(self) -> None:
        registry = build_registry([PRACTICARE], [tool()])
        with self.assertRaises(TypeError):
            registry.tools["practicare_x_y"] = tool()  # type: ignore[index]

    def test_invalid_app_ids(self) -> None:
        for app_id in ("", "P", "PractiCare", "practi-care", "1app", "a" * 40):
            with self.subTest(app_id=app_id), self.assertRaises(RegistryError):
                build_registry([AppRegistration(app_id=app_id, display_name="X")])

    def test_blank_display_name(self) -> None:
        with self.assertRaises(RegistryError):
            build_registry([AppRegistration(app_id="practicare", display_name="  ")])

    def test_duplicates(self) -> None:
        with self.assertRaisesRegex(RegistryError, "duplicate app_id"):
            build_registry([PRACTICARE, PRACTICARE])
        with self.assertRaisesRegex(RegistryError, "duplicate tool"):
            build_registry([PRACTICARE], [tool(), tool()])

    def test_tool_must_belong_to_registered_app(self) -> None:
        with self.assertRaisesRegex(RegistryError, "unregistered app"):
            build_registry([TAXSNAP], [tool()])

    def test_tool_name_must_be_app_verb_noun(self) -> None:
        for name in ("list_tasks", "practicare_list", "taxsnap_list_tasks", "practicare_List_Tasks", "practicare__x", "practicare_" + "x_" * 40 + "y"):
            with self.subTest(name=name), self.assertRaisesRegex(RegistryError, "tool name"):
                build_registry([PRACTICARE, TAXSNAP], [tool(name=name)])

    def test_tool_requires_description_and_roles(self) -> None:
        with self.assertRaisesRegex(RegistryError, "description"):
            build_registry([PRACTICARE], [tool(description=" ")])
        with self.assertRaisesRegex(RegistryError, "at least one role"):
            build_registry([PRACTICARE], [tool(allowed_roles=frozenset())])
        with self.assertRaisesRegex(RegistryError, "invalid role"):
            build_registry([PRACTICARE], [tool(allowed_roles=frozenset({"nurse", "OWNER"}))])

    def test_write_tools_refused(self) -> None:
        with self.assertRaisesRegex(RegistryError, "write tools"):
            build_registry([PRACTICARE], [tool(read_only=False)])

    def test_schemas_must_be_valid_object_schemas(self) -> None:
        for schema in ({"type": "array"}, {"type": "object", "properties": 5}, {"type": "nonsense"}, {}):
            with self.subTest(schema=schema), self.assertRaises(RegistryError):
                build_registry([PRACTICARE], [tool(input_schema=schema)])
        with self.assertRaisesRegex(RegistryError, "output_schema"):
            build_registry([PRACTICARE], [tool(output_schema={"type": "string"})])

    def test_identity_arguments_refused(self) -> None:
        for field in ("tenant_id", "user_id", "role", "user_role", "permissions"):
            schema = {"type": "object", "properties": {field: {"type": "string"}}}
            with self.subTest(field=field), self.assertRaisesRegex(RegistryError, "identity"):
                build_registry([PRACTICARE], [tool(input_schema=schema)])


class AdapterInterfaceTests(unittest.IsolatedAsyncioTestCase):
    def test_adapter_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            AppAdapter()  # type: ignore[abstract]

    async def test_concrete_adapter(self) -> None:
        class EchoAdapter(AppAdapter):
            app_id = "practicare"

            async def call_tool(self, arguments, context):
                return {"tool": context.tool_name, "cid": context.correlation_id, **arguments}

        context = CallContext(correlation_id="cid-1", app_id="practicare", tool_name="practicare_list_tasks")
        self.assertEqual(
            await EchoAdapter().call_tool({"limit": 1}, context),
            {"tool": "practicare_list_tasks", "cid": "cid-1", "limit": 1},
        )

    def test_adapter_error_codes(self) -> None:
        error = AdapterError("TIMEOUT", "backend did not answer in 8s")
        self.assertEqual((error.code, error.detail), ("TIMEOUT", "backend did not answer in 8s"))
        with self.assertRaises(ValueError):
            AdapterError("SOMETHING_ELSE")


if __name__ == "__main__":
    unittest.main()
