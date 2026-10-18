"""
PractiCare MOC inventory stabilization regressions (2026-10-18, round 2):
grounded inventory answers, independent stock/expiry statuses, Owner/Manager manual CRUD + stock adjustment,
Manager AI create/update/adjust with item resolution and approvals, concurrency, Doctor/Nurse read-only,
tenant isolation and audit. Fixture mirrors the manual-test clinic (Examination Gloves 9/10, Hand Sanitizer
expiring tomorrow). Isolated in-memory SQLite; Gemini replaced by scripted fakes.
"""

import json
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_inventory_ai_and_task_permissions import (  # noqa: E402  (shared fixture helpers)
    Base, FakeGemini, FakeExtractionLLM, EXTRACTED, ROLES, T, Y, _item, models, agent_module,
)
from ai.agent import agent  # noqa: E402
from ai.registry import registry, INVENTORY_WRITE_TOOLS  # noqa: E402
import inventory_service  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

TODAY = date.today()


def d(days):
    return (TODAY + timedelta(days=days)).isoformat()


NOT_FOUND_MSG = "No inventory item matching 'Nitrile Gloves' was found in the current clinic inventory. No stock changes were made."


class Stabilization(Base):
    """Replaces the generic inventory fixture with the manual-test clinic."""

    def setUp(self):
        super().setUp()
        db = self.Session()
        db.query(models.InventoryItem).filter_by(tenant_id=T).delete()
        db.add_all([
            _item("inv-eg", "Examination Gloves", 9, d(6), unit="boxes", supplier="Sample Medical Store", batch_number="EG-201",
                  purchase_price=1100, room_id="room-x1"),
            _item("inv-hs", "Hand Sanitizer", 12, d(1), unit="bottles", supplier="Mock Supplier", batch_number="HS-301"),
            _item("inv-fs", "Test Face Shields", 25, "2027-06-30", unit="pieces"),
            _item("inv-cs", "Cotton Swabs", 140, None, unit="packs"),
            _item("inv-zero", "Suture Kits", 0, d(200), unit="kits"),
            _item("inv-old", "Expired Saline", 30, d(-2), unit="bottles"),
        ])
        db.commit()
        db.close()

    def audits(self, prefix="rest:"):
        db = self.Session()
        try:
            return [(a.tool_name, a.status, a.user_role) for a in db.query(models.AIAuditEvent).order_by(models.AIAuditEvent.timestamp)
                    if a.tool_name.startswith(prefix)]
        finally:
            db.close()

    def pending(self):
        db = self.Session()
        try:
            return db.query(models.AIPendingApproval).count()
        finally:
            db.close()

    def snapshot(self):
        db = self.Session()
        try:
            return sorted((i.id, i.tenant_id, i.item_name, i.current_stock, i.min_threshold, i.unit, i.expiry_date, i.supplier,
                           i.batch_number, str(i.purchase_price), i.room_id) for i in db.query(models.InventoryItem).all())
        finally:
            db.close()

    def run_gemini(self, uid, message, fake):
        db = self.Session()
        try:
            with mock.patch.object(agent_module, "get_gemini_llm", return_value=(fake, "fake-gemini")), \
                 mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "test-only-not-a-key"}):
                return agent.run(message=message, conversation_history=[], context=self.ctx(uid, ROLES[uid]), db=db, agent_mode="gemini")
        finally:
            db.close()

    def run_deterministic(self, uid, message):
        db = self.Session()
        try:
            return agent.run(message=message, conversation_history=[], context=self.ctx(uid, ROLES[uid]), db=db, agent_mode="deterministic")
        finally:
            db.close()

    def reject(self, uid, approval_id):
        return self.client.post("/api/v1/ai/approve", headers=self.h(uid), json={"approval_id": approval_id, "action": "reject"})


# =====================================================================================================
# Step 2: grounded answers and independent statuses
# =====================================================================================================

class InventoryAnswerAccuracyTests(Stabilization):
    def test_missing_item_answer_is_specific_and_makes_no_global_claim(self):
        res = self.gw("own-x", "CLINIC_OWNER", "get_inventory_status", {"search_query": "Nitrile Gloves"})
        self.assertFalse(res["found"])
        self.assertEqual(res["returned_items_count"], 0)
        self.assertEqual(res["message"], NOT_FOUND_MSG)
        self.assertNotIn("adequately stocked", json.dumps(res["message"]))
        # Catalog-wide facts stay true and are reported separately
        self.assertEqual((res["low_stock_count"], res["out_of_stock_count"]), (1, 1))

    def test_zero_quantity_is_out_of_stock_not_missing(self):
        res = self.gw("kav-x", "NURSE_STAFF", "get_inventory_status", {"search_query": "suture kits"})
        self.assertTrue(res["found"])
        self.assertEqual(res["items"][0]["current_stock"], 0)
        self.assertEqual(res["items"][0]["stock_status"], "Out of Stock")

    def test_false_global_stock_claim_from_the_model_is_corrected(self):
        plan = AIMessage(content="", tool_calls=[{"name": "get_inventory_status", "args": {"search_query": "Nitrile Gloves"}, "id": "c1"}])
        claim = ("There are no items matching \"Nitrile Gloves\" in the catalog. "
                 "All 6 catalog items currently in the system are adequately stocked above their respective thresholds.")
        result = self.run_gemini("own-x", "How many Nitrile Gloves boxes are available?", FakeGemini([plan], claim))
        self.assertNotIn("adequately stocked", result["reply"])
        self.assertIn("at or below their minimum threshold", result["reply"])
        self.assertEqual(self.item("inv-eg").current_stock, 9)

    def test_not_found_statement_is_added_when_the_model_omits_it(self):
        plan = AIMessage(content="", tool_calls=[{"name": "get_inventory_status", "args": {"search_query": "Nitrile Gloves"}, "id": "c1"}])
        result = self.run_gemini("dem-x", "How many Nitrile Gloves boxes are available?", FakeGemini([plan], "You have 40 boxes available."))
        self.assertIn(NOT_FOUND_MSG, result["reply"])

    def test_stock_and_expiry_statuses_are_independent(self):
        res = self.gw("mgr-x", "INVENTORY_MANAGER", "get_inventory_status", {})
        items = {i["name"]: i for i in res["items"]}
        self.assertEqual((items["Hand Sanitizer"]["stock_status"], items["Hand Sanitizer"]["expiry_state"]), ("In Stock", "Expiring Soon"))
        self.assertEqual((items["Examination Gloves"]["stock_status"], items["Examination Gloves"]["expiry_state"]), ("Low Stock", "Expiring Soon"))
        self.assertEqual(items["Examination Gloves"]["shortfall"], 1)
        self.assertEqual(items["Examination Gloves"]["location"], "Room 101 (Exam 101)")
        self.assertEqual((items["Expired Saline"]["stock_status"], items["Expired Saline"]["expiry_state"]), ("In Stock", "Expired"))
        self.assertEqual(items["Cotton Swabs"]["expiry_state"], "No Expiry Date")
        self.assertEqual(items["Test Face Shields"]["expiry_state"], "Valid")
        self.assertEqual(items["Suture Kits"]["stock_status"], "Out of Stock")
        self.assertNotIn("OK", {i["stock_status"] for i in res["items"]})

        rest = {i["item_name"]: i for i in self.client.get("/api/v1/inventory", headers=self.h("kav-x")).json()}
        for name, item in items.items():
            self.assertEqual((rest[name]["stock_status"], rest[name]["expiry_state"]), (item["stock_status"], item["expiry_state"]), name)

    def test_expiring_soon_boundary(self):
        self.assertEqual(inventory_service.expiry_state(d(30)), "Expiring Soon")
        self.assertEqual(inventory_service.expiry_state(d(31)), "Valid")
        self.assertEqual(inventory_service.expiry_state(d(0)), "Expiring Soon")
        self.assertEqual(inventory_service.expiry_state(d(-1)), "Expired")
        self.assertEqual(inventory_service.stock_status(10, 10), "Low Stock")
        self.assertEqual(inventory_service.stock_status(11, 10), "In Stock")

    def test_deterministic_low_stock_answer_is_grounded(self):
        result = self.run_deterministic("dem-x", "Which items are low stock?")
        self.assertIn("Examination Gloves", result["reply"])
        self.assertIn("Low Stock", result["reply"])
        self.assertNotIn("adequately stocked", result["reply"])
        self.assertNotIn("Cotton Swabs", result["reply"])


# =====================================================================================================
# Step 3 & 5: manual management (REST) and the permission matrix
# =====================================================================================================

class ManualInventoryManagementTests(Stabilization):
    def test_owner_and_manager_full_manual_management(self):
        for uid in ("own-x", "mgr-x"):
            h = self.h(uid)
            created = self.client.post("/api/v1/inventory", headers=h, json={
                "item_name": f"Gauze {uid}", "current_stock": 5, "min_threshold": 2, "unit": "packs",
                "expiry_date": d(90), "supplier": "MedCo", "batch_number": "G1", "purchase_price": "3.50"})
            self.assertEqual(created.status_code, 201, created.text)
            iid = created.json()["id"]
            self.assertTrue(created.json()["can_manage"])

            # Partial edit changes only the sent fields
            edit = self.client.put(f"/api/v1/inventory/{iid}", headers=h, json={"supplier": "NewCo", "min_threshold": 4})
            self.assertEqual(edit.status_code, 200, edit.text)
            row = self.item(iid)
            self.assertEqual((row.supplier, row.min_threshold, row.batch_number, row.unit, row.current_stock, str(row.purchase_price)),
                             ("NewCo", 4, "G1", "packs", 5, "3.50"))

            # Optional fields stay nullable
            self.assertEqual(self.client.put(f"/api/v1/inventory/{iid}", headers=h, json={"expiry_date": "", "batch_number": None}).status_code, 200)
            self.assertEqual((self.item(iid).expiry_date, self.item(iid).batch_number), (None, None))

            # Restock and controlled reduction
            up = self.client.post(f"/api/v1/inventory/{iid}/adjust", headers=h, json={"quantity_change": 15, "expected_current_stock": 5})
            self.assertEqual((up.status_code, up.json()["current_stock"]), (200, 20), up.text)
            down = self.client.post(f"/api/v1/inventory/{iid}/adjust", headers=h, json={"quantity_change": -8, "reason": "used"})
            self.assertEqual(down.json()["current_stock"], 12)

            self.assertEqual(self.client.delete(f"/api/v1/inventory/{iid}", headers=h).status_code, 204)
            self.assertIsNone(self.item(iid))
        actions = [a[0] for a in self.audits() if a[1] == "ALLOWED"]
        for action in ("rest:inventory.create", "rest:inventory.update", "rest:inventory.adjust", "rest:inventory.delete"):
            self.assertEqual(actions.count(action), {"rest:inventory.update": 4, "rest:inventory.adjust": 4}.get(action, 2), action)

    def test_stock_never_negative_and_validation(self):
        h = self.h("mgr-x")
        res = self.client.post("/api/v1/inventory/inv-eg/adjust", headers=h, json={"quantity_change": -10})
        self.assertEqual(res.status_code, 409)
        self.assertIn("only 9", res.json()["detail"])
        self.assertEqual(self.client.put("/api/v1/inventory/inv-eg", headers=h, json={"current_stock": -1}).status_code, 422)
        self.assertEqual(self.client.put("/api/v1/inventory/inv-eg", headers=h, json={"purchase_price": "1.234"}).status_code, 422)
        self.assertEqual(self.client.put("/api/v1/inventory/inv-eg", headers=h, json={"expiry_date": "31/12/2027"}).status_code, 422)
        self.assertEqual(self.client.post("/api/v1/inventory/inv-eg/adjust", headers=h, json={"quantity_change": 0}).status_code, 422)
        self.assertEqual(self.item("inv-eg").current_stock, 9)

    def test_concurrent_manual_changes_are_never_silently_lost(self):
        h = self.h("mgr-x")
        # Someone restocks while another user still has the edit form open showing 9
        self.client.post("/api/v1/inventory/inv-eg/adjust", headers=h, json={"quantity_change": 6})
        stale_edit = self.client.put("/api/v1/inventory/inv-eg", headers=h, json={"current_stock": 12, "expected_current_stock": 9})
        self.assertEqual(stale_edit.status_code, 409)
        stale_adjust = self.client.post("/api/v1/inventory/inv-eg/adjust", headers=h, json={"quantity_change": -1, "expected_current_stock": 9})
        self.assertEqual(stale_adjust.status_code, 409)
        self.assertEqual(self.item("inv-eg").current_stock, 15)
        self.assertIn(("rest:inventory.update", "BLOCKED", "INVENTORY_MANAGER"), self.audits())

    def test_atomic_adjustments_from_stale_sessions_add_up(self):
        a, b = self.Session(), self.Session()
        try:
            a.query(models.InventoryItem).filter_by(id="inv-eg").first()  # both sessions loaded stock=9
            b.query(models.InventoryItem).filter_by(id="inv-eg").first()
            self.assertEqual(inventory_service.adjust_stock(a, T, "inv-eg", 5), (9, 14))
            self.assertEqual(inventory_service.adjust_stock(b, T, "inv-eg", -3), (14, 11))
        finally:
            a.close()
            b.close()
        self.assertEqual(self.item("inv-eg").current_stock, 11)

    def test_doctor_and_nurse_cannot_mutate_and_attempts_are_audited(self):
        before = self.snapshot()
        for uid in ("dem-x", "kav-x"):
            h = self.h(uid)
            calls = [
                self.client.post("/api/v1/inventory", headers=h, json={"item_name": "X", "current_stock": 1, "unit": "u"}),
                self.client.put("/api/v1/inventory/inv-eg", headers=h, json={"supplier": "Evil"}),
                self.client.post("/api/v1/inventory/inv-eg/adjust", headers=h, json={"quantity_change": -9}),
                self.client.delete("/api/v1/inventory/inv-eg", headers=h),
                self.client.post("/api/v1/inventory/import/extract", headers=h, json={"source_type": "text", "text": "gloves 1 box"}),
            ]
            self.assertEqual([c.status_code for c in calls], [403] * 5, uid)
            listing = self.client.get("/api/v1/inventory?expiry=within_30&search=gloves", headers=h)
            self.assertEqual(listing.status_code, 200)
            self.assertTrue(listing.json() and all(i["can_manage"] is False for i in listing.json()))
        self.assertEqual(self.snapshot(), before)
        blocked = [a for a in self.audits() if a[1] == "BLOCKED"]
        self.assertEqual(len(blocked), 10)
        self.assertEqual({a[2] for a in blocked}, {"ATTENDING_PHYSICIAN", "NURSE_STAFF"})

    def test_ui_permission_flags_match_backend_authorization(self):
        for uid, can in (("own-x", True), ("mgr-x", True), ("dem-x", False), ("kav-x", False)):
            items = self.client.get("/api/v1/inventory", headers=self.h(uid)).json()
            self.assertEqual({i["can_manage"] for i in items}, {can}, uid)
            code = self.client.put("/api/v1/inventory/inv-cs", headers=self.h(uid), json={"min_threshold": 3}).status_code
            self.assertEqual(code == 200, can, uid)

    def test_search_and_filters_for_every_role(self):
        for uid in ROLES:
            res = self.client.get("/api/v1/inventory?search=medical", headers=self.h(uid)).json()
            self.assertEqual([i["id"] for i in res], ["inv-eg"], uid)  # supplier match
            res = self.client.get("/api/v1/inventory?search=HS-301", headers=self.h(uid)).json()
            self.assertEqual([i["id"] for i in res], ["inv-hs"], uid)  # batch match
            res = self.client.get("/api/v1/inventory?low_stock_only=true", headers=self.h(uid)).json()
            self.assertEqual({i["id"] for i in res}, {"inv-eg", "inv-zero"}, uid)

    def test_manual_operations_are_tenant_isolated(self):
        h = self.h("mgr-x")
        self.assertEqual(self.client.put("/api/v1/inventory/inv-y", headers=h, json={"supplier": "X"}).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/inventory/inv-y/adjust", headers=h, json={"quantity_change": -1}).status_code, 404)
        self.assertEqual(self.client.delete("/api/v1/inventory/inv-y", headers=h).status_code, 404)
        self.assertEqual(self.client.get("/api/v1/inventory/inv-y", headers=h).status_code, 404)
        self.assertNotIn("inv-y", [i["id"] for i in self.client.get("/api/v1/inventory?search=gloves", headers=h).json()])
        self.assertEqual(self.item("inv-y").current_stock, 999)


# =====================================================================================================
# Step 4: Manager AI chat management through the Tool Gateway
# =====================================================================================================

class InventoryAIManagementTests(Stabilization):
    def test_update_by_item_name_shows_exact_change_and_persists_once(self):
        res = self.gw("mgr-x", "INVENTORY_MANAGER", "update_inventory_item",
                      {"item_query": "examination gloves", "min_threshold": 20, "supplier": "Demo Medical Supplies"})
        self.assertEqual(res["status"], "APPROVAL_REQUIRED", res)
        self.assertEqual(res["arguments"]["item_id"], "inv-eg")
        self.assertIn("'Examination Gloves' (inv-eg)", res["description"])
        self.assertIn("min_threshold: 10 → 20", res["description"])
        self.assertIn("supplier: Sample Medical Store → Demo Medical Supplies", res["description"])
        self.assertEqual(self.item("inv-eg").min_threshold, 10)
        out = self.approve("mgr-x", res["approval_id"]).json()
        self.assertEqual(out["status"], "EXECUTED", out)
        self.assertIn("min_threshold 10 → 20", out["reply"])
        row = self.item("inv-eg")
        self.assertEqual((row.min_threshold, row.supplier, row.current_stock, row.batch_number), (20, "Demo Medical Supplies", 9, "EG-201"))
        self.assertNotEqual(self.approve("mgr-x", res["approval_id"]).status_code, 200)  # executes once only

    def test_expiry_update_and_restock_by_name(self):
        upd = self.gw("own-x", "CLINIC_OWNER", "update_inventory_item", {"item_query": "Hand Sanitizer", "expiry_date": "2027-01-15"})
        self.assertIn(f"expiry_date: {d(1)} → 2027-01-15", upd["description"])
        self.assertEqual(self.approve("own-x", upd["approval_id"]).json()["status"], "EXECUTED")
        self.assertEqual(self.item("inv-hs").expiry_date, "2027-01-15")

        adj = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_query": "Examination Gloves", "quantity_change": 15})
        for text in ("Restock 'Examination Gloves' (inv-eg)", "Current quantity: 9 boxes", "Adjustment: +15 boxes",
                     "New quantity after approval: 24 boxes"):
            self.assertIn(text, adj["description"])
        self.assertEqual(adj["arguments"]["expected_current_stock"], 9)
        out = self.approve("mgr-x", adj["approval_id"]).json()
        self.assertEqual(out["status"], "EXECUTED", out)
        self.assertIn("from 9 to 24 boxes", out["reply"])
        self.assertEqual(self.item("inv-eg").current_stock, 24)

    def test_rejected_approval_changes_nothing(self):
        before = self.snapshot()
        adj = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_id": "inv-eg", "quantity_change": 15})
        self.assertEqual(self.reject("mgr-x", adj["approval_id"]).json()["status"], "REJECTED")
        self.assertNotEqual(self.approve("mgr-x", adj["approval_id"]).status_code, 200)
        self.assertEqual(self.snapshot(), before)

    def test_approval_is_refused_if_stock_changed_after_it_was_shown(self):
        adj = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_id": "inv-eg", "quantity_change": 15})
        self.client.post("/api/v1/inventory/inv-eg/adjust", headers=self.h("own-x"), json={"quantity_change": 1})
        out = self.approve("mgr-x", adj["approval_id"]).json()
        self.assertEqual(out["status"], "FAILED")
        self.assertIn("changed from 9 to 10", out["detail"])
        self.assertEqual(self.item("inv-eg").current_stock, 10)

    def test_update_is_refused_if_fields_changed_after_approval_was_shown(self):
        upd = self.gw("mgr-x", "INVENTORY_MANAGER", "update_inventory_item", {"item_id": "inv-eg", "supplier": "Demo Medical Supplies"})
        self.client.put("/api/v1/inventory/inv-eg", headers=self.h("own-x"), json={"supplier": "Owner Choice"})
        out = self.approve("mgr-x", upd["approval_id"]).json()
        self.assertEqual(out["status"], "FAILED")
        self.assertIn("changed by someone else", out["detail"])
        self.assertEqual(self.item("inv-eg").supplier, "Owner Choice")

    def test_ambiguous_and_missing_items_are_never_guessed_or_created(self):
        db = self.Session()
        db.add(_item("inv-eg2", "Examination Gloves Large", 30, d(100), unit="boxes"))
        db.commit()
        db.close()
        before = self.snapshot()
        amb = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_query": "gloves", "quantity_change": 5})
        self.assertEqual(amb["error"], "AMBIGUOUS_ITEM", amb)
        self.assertEqual({c["item_id"] for c in amb["candidates"]}, {"inv-eg", "inv-eg2"})
        # An exact name match is not ambiguous
        exact = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_query": "Examination Gloves", "quantity_change": 5})
        self.assertEqual(exact["arguments"]["item_id"], "inv-eg")
        self.reject("mgr-x", exact["approval_id"])
        missing = self.gw("mgr-x", "INVENTORY_MANAGER", "update_inventory_item", {"item_query": "Nitrile Gloves", "min_threshold": 5})
        self.assertEqual(missing["error"], "NOT_FOUND")
        fake_id = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_id": "inv-invented", "quantity_change": 5})
        self.assertEqual(fake_id["error"], "NOT_FOUND")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.pending(), 1)  # only the exact-match request created (then rejected) an approval

    def test_agent_never_creates_an_item_unless_explicitly_asked(self):
        rogue = AIMessage(content="", tool_calls=[{"name": "create_inventory_item",
                                                    "args": {"item_name": "Nitrile Gloves", "quantity": 15, "unit": "boxes"}, "id": "c1"}])
        result = self.run_gemini("mgr-x", "Add 15 boxes to Nitrile Gloves stock", FakeGemini([rogue], "Done."))
        self.assertEqual([t["status"] for t in result["tool_calls_executed"]], ["FAILED"])
        db = self.Session()
        self.assertIsNone(db.query(models.InventoryItem).filter_by(item_name="Nitrile Gloves").first())
        blocked = db.query(models.AIAuditEvent).filter_by(tool_name="create_inventory_item", status="BLOCKED").count()
        db.close()
        self.assertEqual(blocked, 1)

    def test_agent_creates_when_explicitly_asked_and_reports_verified_values(self):
        plan = AIMessage(content="", tool_calls=[{"name": "create_inventory_item", "args": {
            "item_name": "Test Face Shields XL", "quantity": 25, "unit": "pieces", "expiry_date": "2027-06-30"}, "id": "c1"}])
        result = self.run_gemini("mgr-x", "Create an inventory item named Test Face Shields XL with 25 pieces and expiry date 2027-06-30.",
                                 FakeGemini([plan], "Created Test Face Shields XL with 25 pieces."))
        self.assertEqual([t["status"] for t in result["tool_calls_executed"]], ["SUCCESS"])
        db = self.Session()
        row = db.query(models.InventoryItem).filter_by(item_name="Test Face Shields XL").one()
        db.close()
        self.assertEqual((row.tenant_id, row.current_stock, row.unit, row.expiry_date), (T, 25, "pieces", "2027-06-30"))

    def test_doctor_and_nurse_tool_exposure_is_read_only(self):
        for role in ("ATTENDING_PHYSICIAN", "NURSE_STAFF"):
            names = {t.name for t in registry.get_tools_for_role(role)}
            self.assertIn("get_inventory_status", names)
            self.assertFalse(names & INVENTORY_WRITE_TOOLS, role)
        for role in ("CLINIC_OWNER", "INVENTORY_MANAGER"):
            self.assertTrue(INVENTORY_WRITE_TOOLS <= {t.name for t in registry.get_tools_for_role(role)}, role)
        # Server-set approval pins are never exposed to the model
        schema = json.dumps([registry.get(n).to_openai_schema() for n in ("update_inventory_item", "adjust_inventory_stock")])
        self.assertNotIn("expected_current_stock", schema)
        self.assertNotIn("expected_values", schema)

    def test_doctor_and_nurse_ai_writes_denied_without_mutation(self):
        before = self.snapshot()
        for uid in ("dem-x", "kav-x"):
            for tool, args in (("update_inventory_item", {"item_query": "Examination Gloves", "min_threshold": 1}),
                               ("adjust_inventory_stock", {"item_query": "Examination Gloves", "quantity_change": -9}),
                               ("create_inventory_item", {"item_name": "X", "quantity": 1, "unit": "u"})):
                self.assertEqual(self.gw(uid, ROLES[uid], tool, args).get("error"), "FORBIDDEN", (uid, tool))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.pending(), 0)

    def test_ai_operations_are_tenant_isolated(self):
        before = self.snapshot()
        for tool, args in (("update_inventory_item", {"item_id": "inv-y", "supplier": "X"}),
                           ("update_inventory_item", {"item_query": "Tenant Y Gloves", "supplier": "X"}),
                           ("adjust_inventory_stock", {"item_query": "Tenant Y Gloves", "quantity_change": 1})):
            self.assertEqual(self.gw("mgr-x", "INVENTORY_MANAGER", tool, args).get("error"), "NOT_FOUND", (tool, args))
        y = self.gw("mgr-y", "INVENTORY_MANAGER", "get_inventory_status", {"search_query": "Examination Gloves"}, tenant=Y)
        self.assertFalse(y["found"])
        self.assertEqual(self.snapshot(), before)

    def test_import_confirmation_persists_and_is_visible_immediately(self):
        fake = FakeExtractionLLM(EXTRACTED)
        with mock.patch.object(inventory_service, "get_extraction_llm", return_value=(fake, "f")):
            prev = self.client.post("/api/v1/inventory/import/extract", headers=self.h("mgr-x"),
                                    json={"source_type": "text", "text": "gauze 200 packs"}).json()
        row = next(r for r in prev["rows"] if r["row_id"] == "row-1")
        out = self.client.post("/api/v1/inventory/import/confirm", headers=self.h("mgr-x"), json={
            "import_token": prev["import_token"], "source_hash": prev["source_hash"], "source_type": "text",
            "rows": [{"row_id": "row-1", "action": "create", **row["values"]}]}).json()
        self.assertEqual(out["counts"]["created"], 1)
        listed = {i["item_name"]: i for i in self.client.get("/api/v1/inventory?search=gauze", headers=self.h("kav-x")).json()}
        self.assertEqual((listed["Sterile Gauze Pads"]["current_stock"], listed["Sterile Gauze Pads"]["supplier"],
                          listed["Sterile Gauze Pads"]["purchase_price"]), (200, "MedCo", 1.25))
        self.assertIn(("rest:inventory.import", "ALLOWED", "INVENTORY_MANAGER"), self.audits())


if __name__ == "__main__":
    unittest.main()
