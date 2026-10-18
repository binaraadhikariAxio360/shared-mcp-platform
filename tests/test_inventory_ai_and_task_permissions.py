"""
PractiCare MOC regressions (2026-10-18): AI inventory import, expiry filters, inventory AI chat permissions,
Doctor task deletion lineage and Manager-to-Doctor reassignment.
Isolated in-memory SQLite; Gemini is replaced by scripted fakes (no network, no quota, no real data).
"""

import base64
import json
import os
import sys
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

BACKEND_DIR = Path(__file__).resolve().parents[1] / "apps" / "practicare" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from practicare_phase0_harness import PractiCareIsolatedTestCase, models
from security import create_access_token
from ai.context import SecurityContext
from ai.gateway import gateway
from ai.agent import agent
from ai.registry import registry, INVENTORY_WRITE_TOOLS
import inventory_service
from langchain_core.messages import AIMessage

agent_module = sys.modules["ai.agent"]
T, Y = "tenant-x", "tenant-y"
TODAY = date.today()


def d(days):
    return (TODAY + timedelta(days=days)).isoformat()


def _user(uid, role, tenant=T):
    return models.User(id=uid, email=f"{uid}@test.local", password_hash="not-used", full_name=uid, role=role,
                       tenant_id=tenant, company_name=tenant, membership_status="APPROVED", is_active=True)


def _staff(sid, name, role, uid, tenant=T):
    return models.Staff(id=sid, name=name, role=role, user_id=uid, practice_id=f"prac-{tenant}", tenant_id=tenant)


def _item(iid, name, stock, expiry=None, tenant=T, **kw):
    return models.InventoryItem(id=iid, item_name=name, current_stock=stock, min_threshold=kw.pop("min_threshold", 10),
                                unit=kw.pop("unit", "boxes"), expiry_date=expiry, practice_id=f"prac-{tenant}",
                                tenant_id=tenant, **kw)


def _task(tid, title, assigned=None, role=None, uid=None, due="2026-10-20"):
    return models.Task(id=tid, title=title, status="Pending", due_date=due, assigned_staff_id=assigned,
                       created_by_role=role, created_by_user_id=uid, practice_id=f"prac-{T}", tenant_id=T)


def cell(value, confidence="high"):
    return {"value": value, "confidence": confidence}


class FakeExtractionLLM:
    """Stands in for the Gemini chat model used by inventory_service.extract_inventory_records."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return AIMessage(content=f"```json\n{text}\n```")


class FakeGemini:
    """Scripted stand-in for the agent's Gemini model; records the tool schemas it was given."""

    def __init__(self, planning_replies, synthesis_text):
        self.planning = list(planning_replies)
        self.synthesis_text = synthesis_text
        self.bound_tool_names = []

    def bind_tools(self, schemas):
        self.bound_tool_names.append([s["function"]["name"] for s in schemas])
        fake = self

        class Bound:
            def invoke(self, messages):
                return fake.planning.pop(0) if fake.planning else AIMessage(content=fake.synthesis_text)
        return Bound()

    def invoke(self, messages):
        return AIMessage(content=self.synthesis_text)


class Base(PractiCareIsolatedTestCase):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add_all([
            models.Practice(id=f"prac-{T}", name="Clinic X", location="X", tenant_id=T),
            models.Practice(id=f"prac-{Y}", name="Clinic Y", location="Y", tenant_id=Y),
            _user("own-x", "CLINIC_OWNER"), _user("mgr-x", "INVENTORY_MANAGER"),
            _user("dem-x", "PHYSICIAN"), _user("rac-x", "ATTENDING_PHYSICIAN"), _user("kav-x", "NURSE_STAFF"),
            _user("own-y", "CLINIC_OWNER", Y), _user("mgr-y", "INVENTORY_MANAGER", Y),
            _staff("s-own", "Owner X", "Staff", "own-x"), _staff("s-mgr", "Sagy", "Inventory Manager", "mgr-x"),
            _staff("s-dem", "Dr. Dem", "Doctor", "dem-x"), _staff("s-rac", "Dr. Racini", "Doctor", "rac-x"),
            _staff("s-kav", "Kavi", "Nurse", "kav-x"), _staff("s-own-y", "Owner Y", "Staff", "own-y", Y),
            models.Room(id="room-x1", room_number="101", name="Exam 101", practice_id=f"prac-{T}", tenant_id=T),
            models.Room(id="room-y1", room_number="901", name="Y Room", practice_id=f"prac-{Y}", tenant_id=Y),
            _item("inv-exp", "Expired Saline", 30, d(-3)),
            _item("inv-d0", "Today Gauze", 30, d(0)),
            _item("inv-d5", "Nitrile Gloves", 40, d(5), supplier="MedCo", batch_number="B-100"),
            _item("inv-d20", "Syringes 5ml", 5, d(20)),
            _item("inv-d60", "Alcohol Swabs", 80, d(60)),
            _item("inv-d200", "Face Masks", 100, d(200)),
            _item("inv-none", "Bandage Roll", 15, None),
            _item("inv-legacy", "Legacy Tape", 15, "Nov 2026"),
            _item("inv-y", "Tenant Y Gloves", 999, d(5), tenant=Y),
        ])
        db.commit()
        db.close()

    def h(self, uid, tenant=T):
        db = self.Session()
        role = db.query(models.User).filter_by(id=uid).first().role
        db.close()
        return {"Authorization": f"Bearer {create_access_token(uid, tenant, role)}"}

    def ctx(self, uid, role, tenant=T):
        return SecurityContext.create(tenant, uid, role)

    def item(self, iid):
        db = self.Session()
        try:
            return db.query(models.InventoryItem).filter_by(id=iid).first()
        finally:
            db.close()

    def count_items(self, tenant=T):
        db = self.Session()
        try:
            return db.query(models.InventoryItem).filter_by(tenant_id=tenant).count()
        finally:
            db.close()

    def gw(self, uid, role, tool, args, tenant=T):
        db = self.Session()
        try:
            return gateway.execute(tool, args, self.ctx(uid, role, tenant), db)
        finally:
            db.close()

    def approve(self, uid, approval_id, tenant=T):
        return self.client.post("/api/v1/ai/approve", headers=self.h(uid, tenant),
                                json={"approval_id": approval_id, "action": "approve"})


# =====================================================================================================
# Part 2: expiry filters and sorting
# =====================================================================================================

class InventoryExpiryFilterTests(Base):
    def ids(self, query, uid="mgr-x"):
        res = self.client.get(f"/api/v1/inventory{query}", headers=self.h(uid))
        self.assertEqual(res.status_code, 200, res.text)
        return [i["id"] for i in res.json()]

    def test_each_expiry_filter_returns_exactly_the_matching_items(self):
        self.assertEqual(set(self.ids("")), {"inv-exp", "inv-d0", "inv-d5", "inv-d20", "inv-d60", "inv-d200", "inv-none", "inv-legacy"})
        self.assertEqual(set(self.ids("?expiry=expired")), {"inv-exp"})
        self.assertEqual(set(self.ids("?expiry=within_7")), {"inv-d0", "inv-d5"})
        self.assertEqual(set(self.ids("?expiry=within_30")), {"inv-d0", "inv-d5", "inv-d20"})
        self.assertEqual(set(self.ids("?expiry=within_90")), {"inv-d0", "inv-d5", "inv-d20", "inv-d60"})
        self.assertEqual(set(self.ids("?expiry=none")), {"inv-none", "inv-legacy"})
        self.assertEqual(set(self.ids("?expiry=all")), set(self.ids("")))

    def test_sort_by_nearest_expiry_puts_expired_first_and_no_expiry_last(self):
        self.assertEqual(self.ids("?sort=expiry"),
                         ["inv-exp", "inv-d0", "inv-d5", "inv-d20", "inv-d60", "inv-d200", "inv-none", "inv-legacy"])
        self.assertEqual(self.ids("?expiry=within_30&sort=expiry"), ["inv-d0", "inv-d5", "inv-d20"])

    def test_server_computed_expiry_fields(self):
        rows = {i["id"]: i for i in self.client.get("/api/v1/inventory", headers=self.h("kav-x")).json()}
        self.assertTrue(rows["inv-exp"]["is_expired"])
        self.assertEqual(rows["inv-exp"]["expiry_status"], "expired")
        self.assertEqual(rows["inv-d5"]["days_to_expiry"], 5)
        self.assertEqual(rows["inv-d5"]["expiry_status"], "within_7")
        self.assertEqual(rows["inv-d60"]["expiry_status"], "within_90")
        self.assertEqual(rows["inv-legacy"]["expiry_status"], "none")
        self.assertTrue(rows["inv-d20"]["is_expiring_soon"])
        self.assertFalse(rows["inv-exp"]["is_expiring_soon"])

    def test_window_boundaries_are_inclusive(self):
        self.assertTrue(inventory_service.matches_expiry_filter(d(7), "within_7", TODAY))
        self.assertFalse(inventory_service.matches_expiry_filter(d(8), "within_7", TODAY))
        self.assertTrue(inventory_service.matches_expiry_filter(d(0), "within_7", TODAY))
        self.assertFalse(inventory_service.matches_expiry_filter(d(-1), "within_7", TODAY))
        self.assertTrue(inventory_service.matches_expiry_filter(d(-1), "expired", TODAY))

    def test_invalid_filter_rejected_and_all_roles_can_filter(self):
        self.assertEqual(self.client.get("/api/v1/inventory?expiry=soonish", headers=self.h("mgr-x")).status_code, 422)
        for uid in ("own-x", "mgr-x", "dem-x", "kav-x"):
            self.assertEqual(set(self.ids("?expiry=expired", uid)), {"inv-exp"}, uid)

    def test_filters_never_leak_other_tenant_items(self):
        self.assertNotIn("inv-y", self.ids("?expiry=within_7&sort=expiry"))

    def test_dashboard_expiring_count_uses_the_same_rule(self):
        summary = self.client.get("/api/v1/dashboard/summary", headers=self.h("own-x")).json()
        self.assertEqual(summary["expiring_soon_count"], len(self.ids("?expiry=within_30")))


# =====================================================================================================
# Part 1: AI import - extraction, preview, confirmation, duplicates, validation
# =====================================================================================================

PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

EXTRACTED = {"items": [
    {"item_name": cell("Sterile Gauze Pads"), "quantity": cell(200), "unit": cell("packs"), "expiry_date": cell("2028-01-31"),
     "purchase_price": cell("$1.25"), "supplier": cell("MedCo"), "batch_number": cell("GZ-77")},
    {"item_name": cell("Nitrile Gloves"), "quantity": cell(10), "unit": cell("boxes"), "expiry_date": cell(d(5)),
     "purchase_price": cell(None, "low"), "supplier": cell("MedCo"), "batch_number": cell("B-100")},
    {"item_name": cell("Lidocaine 2%"), "quantity": cell(12, "low"), "unit": cell(None, "low"), "expiry_date": cell("03/04/2027", "medium"),
     "purchase_price": cell(None, "low"), "supplier": cell(None, "low"), "batch_number": cell(None, "low")},
    {"item_name": cell("sterile gauze  pads"), "quantity": cell(5), "unit": cell("packs"), "expiry_date": cell("2028-01-31"),
     "purchase_price": cell(None, "low"), "supplier": cell(None, "low"), "batch_number": cell("gz-77")},
], "notes": ""}


class InventoryImportTests(Base):
    def extract(self, uid="mgr-x", payload=EXTRACTED, **body):
        fake = FakeExtractionLLM(payload)
        with mock.patch.object(inventory_service, "get_extraction_llm", return_value=(fake, "fake-gemini")):
            res = self.client.post("/api/v1/inventory/import/extract", headers=self.h(uid), json=body)
        return res, fake

    def extract_text(self, uid="mgr-x", payload=EXTRACTED):
        return self.extract(uid, payload, source_type="text", text="gauze 200 packs ...")

    def confirm(self, preview, rows, uid="mgr-x", tenant=T, token=None):
        return self.client.post("/api/v1/inventory/import/confirm", headers=self.h(uid, tenant), json={
            "import_token": token or preview["import_token"], "source_hash": preview["source_hash"],
            "source_type": preview["source_type"], "rows": rows,
        })

    @staticmethod
    def row(preview_row, **overrides):
        r = {"row_id": preview_row["row_id"], "action": preview_row["action"],
             "existing_item_id": preview_row["match"].get("existing_item_id"), **preview_row["values"]}
        r.update(overrides)
        return r

    # --- extraction from each source type ---------------------------------------------------------

    def test_text_extraction_builds_multi_item_preview_with_flags_and_writes_nothing(self):
        before = self.count_items()
        res, fake = self.extract_text()
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(self.count_items(), before)
        rows = {r["row_id"]: r for r in body["rows"]}
        self.assertEqual(len(rows), 4)
        self.assertEqual(len(body["source_hash"]), 64)
        self.assertGreaterEqual(len(body["import_token"]), 16)

        gauze = rows["row-1"]
        self.assertEqual(gauze["values"]["purchase_price"], 1.25)
        self.assertEqual(gauze["action"], "create")
        self.assertEqual(gauze["match"]["status"], "new")

        gloves = rows["row-2"]  # same name + batch + expiry as inv-d5
        self.assertEqual(gloves["match"]["status"], "existing_match")
        self.assertEqual(gloves["match"]["existing_item_id"], "inv-d5")
        self.assertEqual(gloves["action"], "skip")
        self.assertIsNone(gloves["values"]["purchase_price"])  # missing stays missing

        lido = rows["row-3"]
        self.assertIsNone(lido["values"]["unit"])
        self.assertEqual(lido["values"]["expiry_date"], "03/04/2027")  # ambiguous: kept as written, not guessed
        issues = {(i["field"], i["level"]) for i in lido["issues"]}
        self.assertIn(("unit", "error"), issues)
        self.assertIn(("expiry_date", "error"), issues)
        self.assertIn(("quantity", "warning"), issues)  # low confidence flagged
        self.assertEqual(lido["confidence"]["unit"], "missing")

        dup = rows["row-4"]  # same lot as row-1 (case/space-insensitive)
        self.assertEqual(dup["match"]["status"], "duplicate_in_import")
        self.assertEqual(dup["action"], "skip")

        prompt_text = fake.calls[0][0].content[0]["text"]
        self.assertIn("NEVER guess", prompt_text)

    def test_pdf_and_image_are_sent_to_gemini_as_files(self):
        res, fake = self.extract(source_type="pdf", filename="invoice.pdf", content_base64=base64.b64encode(PDF_BYTES).decode())
        self.assertEqual(res.status_code, 200, res.text)
        block = fake.calls[0][0].content[1]
        self.assertEqual(block["mime_type"], "application/pdf")
        self.assertEqual(base64.b64decode(block["data"]), PDF_BYTES)

        res, fake = self.extract(source_type="image", mime_type="image/jpeg", content_base64=base64.b64encode(PNG_BYTES).decode())
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(fake.calls[0][0].content[1]["mime_type"], "image/png")  # sniffed from the bytes
        self.assertEqual(len(res.json()["rows"]), 4)

    def test_invalid_sources_are_rejected_before_ai(self):
        res, fake = self.extract(source_type="pdf", content_base64=base64.b64encode(b"not a pdf").decode())
        self.assertEqual(res.status_code, 400)
        self.assertEqual(fake.calls, [])
        res, _ = self.extract(source_type="image", content_base64="%%%not-base64%%%")
        self.assertEqual(res.status_code, 400)
        res, _ = self.extract(source_type="image", mime_type="image/gif", content_base64=base64.b64encode(b"GIF89a....").decode())
        self.assertEqual(res.status_code, 400)
        res, _ = self.extract(source_type="text", text="   ")
        self.assertEqual(res.status_code, 400)
        with mock.patch.object(inventory_service, "MAX_FILE_BYTES", 10):
            res, _ = self.extract(source_type="pdf", content_base64=base64.b64encode(PDF_BYTES).decode())
        self.assertEqual(res.status_code, 400)

    def test_ai_unavailable_returns_503_and_invents_nothing(self):
        with mock.patch.object(inventory_service, "get_extraction_llm", side_effect=ValueError("Missing GOOGLE_API_KEY")):
            res = self.client.post("/api/v1/inventory/import/extract", headers=self.h("mgr-x"),
                                   json={"source_type": "text", "text": "gloves 10 boxes"})
        self.assertEqual(res.status_code, 503)
        res, _ = self.extract_text(payload="this is not json")
        self.assertEqual(res.status_code, 503)

    def test_doctor_and_nurse_cannot_extract_or_confirm(self):
        for uid in ("dem-x", "kav-x"):
            res, fake = self.extract_text(uid=uid)
            self.assertEqual(res.status_code, 403, uid)
            self.assertEqual(fake.calls, [])
            res = self.confirm({"import_token": "t" * 32, "source_hash": "a" * 64, "source_type": "text"},
                               [{"row_id": "row-1", "action": "create", "item_name": "X", "quantity": 1, "unit": "u"}], uid=uid)
            self.assertEqual(res.status_code, 403, uid)
        self.assertEqual(self.count_items(), 8)

    # --- confirmation ----------------------------------------------------------------------------

    def test_confirm_creates_valid_rows_rejects_invalid_and_reports_each_row(self):
        preview = self.extract_text()[0].json()
        rows = {r["row_id"]: r for r in preview["rows"]}
        payload = [self.row(rows["row-1"]), self.row(rows["row-2"]), self.row(rows["row-3"]), self.row(rows["row-4"])]
        res = self.confirm(preview, payload)
        self.assertEqual(res.status_code, 200, res.text)
        out = res.json()
        self.assertEqual(out["status"], "IMPORTED")
        self.assertEqual(out["counts"], {"created": 1, "updated": 0, "skipped": 2, "rejected": 1})
        self.assertEqual([r["row_id"] for r in out["rejected"]], ["row-3"])
        self.assertTrue(any("Unit is required" in e for e in out["rejected"][0]["errors"]))
        self.assertTrue(any("YYYY-MM-DD" in e for e in out["rejected"][0]["errors"]))

        created = self.item(out["created"][0]["item_id"])
        self.assertEqual((created.item_name, created.current_stock, created.unit, created.expiry_date),
                         ("Sterile Gauze Pads", 200, "packs", "2028-01-31"))
        self.assertEqual((created.supplier, created.batch_number, created.purchase_price), ("MedCo", "GZ-77", Decimal("1.25")))
        self.assertEqual(created.min_threshold, 10)
        self.assertEqual(self.item("inv-d5").current_stock, 40)  # skipped duplicate untouched
        self.assertEqual(self.count_items(), 9)

    def test_repeated_confirmation_and_repeated_import_never_duplicate(self):
        preview = self.extract_text()[0].json()
        rows = {r["row_id"]: r for r in preview["rows"]}
        self.assertEqual(self.confirm(preview, [self.row(rows["row-1"])]).status_code, 200)
        self.assertEqual(self.count_items(), 9)

        again = self.confirm(preview, [self.row(rows["row-1"])])
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"]["previous_result"]["counts"]["created"], 1)
        self.assertEqual(self.count_items(), 9)

        # Same document extracted again: flagged as previously imported, rows now match existing records
        second = self.extract_text()[0].json()
        self.assertEqual(len(second["previous_imports"]), 1)
        gauze = next(r for r in second["rows"] if r["row_id"] == "row-1")
        self.assertEqual(gauze["match"]["status"], "existing_match")
        self.assertEqual(gauze["action"], "skip")
        # Forcing 'create' anyway is rejected server-side; nothing is recorded or written
        forced = self.confirm(second, [self.row(gauze, action="create")]).json()
        self.assertEqual(forced["status"], "NOTHING_IMPORTED")
        self.assertIn("Duplicate of existing record", forced["rejected"][0]["errors"][0])
        self.assertEqual(self.count_items(), 9)

    def test_restock_adds_quantity_without_overwriting_existing_values(self):
        preview = self.extract_text()[0].json()
        gloves = next(r for r in preview["rows"] if r["row_id"] == "row-2")
        out = self.confirm(preview, [self.row(gloves, action="restock", supplier="OtherCo", purchase_price="0.80")]).json()
        self.assertEqual(out["counts"]["updated"], 1)
        upd = out["updated"][0]
        self.assertEqual((upd["previous_stock"], upd["new_stock"]), (40, 50))
        self.assertEqual(upd["fields_filled"], ["purchase_price"])
        self.assertEqual(upd["kept_existing"], [{"field": "supplier", "kept": "MedCo", "document_value": "OtherCo"}])
        item = self.item("inv-d5")
        self.assertEqual((item.current_stock, item.supplier, item.purchase_price), (50, "MedCo", Decimal("0.80")))

    def test_restock_of_a_different_lot_or_unit_is_rejected(self):
        preview = self.extract_text()[0].json()
        gloves = next(r for r in preview["rows"] if r["row_id"] == "row-2")
        out = self.confirm(preview, [
            self.row(gloves, row_id="a", action="restock", expiry_date=d(400)),
            self.row(gloves, row_id="b", action="restock", unit="pairs"),
            self.row(gloves, row_id="c", action="restock", existing_item_id="inv-y"),
            self.row(gloves, row_id="d", action="restock", quantity=0),
        ]).json()
        self.assertEqual(out["status"], "NOTHING_IMPORTED")
        self.assertEqual(out["counts"]["rejected"], 4)
        self.assertEqual(self.item("inv-d5").current_stock, 40)
        self.assertEqual(self.item("inv-y").current_stock, 999)

    def test_server_side_validation_of_edited_rows(self):
        preview = self.extract_text()[0].json()
        base = {"row_id": "x", "action": "create", "item_name": "Valid Item", "quantity": 3, "unit": "units"}
        out = self.confirm(preview, [
            {**base, "row_id": "neg", "quantity": -4},
            {**base, "row_id": "frac", "quantity": "2.5"},
            {**base, "row_id": "date", "expiry_date": "2027-02-30"},
            {**base, "row_id": "price", "purchase_price": "1.234"},
            {**base, "row_id": "room", "room_id": "room-y1"},
            {**base, "row_id": "noname", "item_name": "  "},
            {**base, "row_id": "ok", "room_id": "room-x1", "expiry_date": d(10), "purchase_price": "4.50"},
        ]).json()
        self.assertEqual({r["row_id"] for r in out["rejected"]}, {"neg", "frac", "date", "price", "room", "noname"})
        self.assertEqual([c["row_id"] for c in out["created"]], ["ok"])

    def test_import_is_tenant_isolated(self):
        preview = self.extract_text()[0].json()
        rows = {r["row_id"]: r for r in preview["rows"]}
        self.confirm(preview, [self.row(rows["row-1"])])
        # Another tenant replaying the token learns nothing and writes nothing
        res = self.confirm(preview, [self.row(rows["row-1"])], uid="mgr-y", tenant=Y)
        self.assertEqual(res.status_code, 409)
        self.assertIsNone(res.json()["detail"]["previous_result"])
        self.assertEqual(self.count_items(Y), 1)
        # Tenant Y's preview never matches tenant X records
        fake = FakeExtractionLLM(EXTRACTED)
        with mock.patch.object(inventory_service, "get_extraction_llm", return_value=(fake, "f")):
            y_prev = self.client.post("/api/v1/inventory/import/extract", headers=self.h("mgr-y", Y),
                                      json={"source_type": "text", "text": "gauze 200 packs ..."}).json()
        self.assertEqual(y_prev["previous_imports"], [])
        self.assertTrue(all(r["match"]["status"] in ("new", "duplicate_in_import") for r in y_prev["rows"]))

    def test_failed_transaction_writes_nothing(self):
        preview = self.extract_text()[0].json()
        rows = {r["row_id"]: r for r in preview["rows"]}
        db = self.Session()
        try:
            with mock.patch.object(db, "commit", side_effect=RuntimeError("db down")):
                with self.assertRaises(RuntimeError):
                    inventory_service.apply_import(
                        db, tenant_id=T, user_id="mgr-x", practice_id=f"prac-{T}", import_token="tok-" + "z" * 20,
                        source_hash=preview["source_hash"], source_type="text",
                        rows=[self.row(rows["row-1"]), self.row(rows["row-2"], action="restock")])
        finally:
            db.close()
        self.assertEqual(self.count_items(), 8)
        self.assertEqual(self.item("inv-d5").current_stock, 40)


# =====================================================================================================
# Part 3: inventory through AI chat (Tool Gateway + agent)
# =====================================================================================================

ROLES = {"own-x": "CLINIC_OWNER", "mgr-x": "INVENTORY_MANAGER", "dem-x": "ATTENDING_PHYSICIAN", "kav-x": "NURSE_STAFF"}


class InventoryAIToolTests(Base):
    def test_all_four_roles_read_real_inventory_with_expiry_filters(self):
        for uid, role in ROLES.items():
            res = self.gw(uid, role, "get_inventory_status", {"expiry_filter": "within_7", "sort_by": "expiry"})
            self.assertEqual(res.get("status"), "SUCCESS", (uid, res))
            self.assertEqual([i["item_id"] for i in res["items"]], ["inv-d0", "inv-d5"], uid)
            self.assertNotIn("inv-y", json.dumps(res))
        details = self.gw("kav-x", "NURSE_STAFF", "get_inventory_status", {"item_id": "inv-d5"})
        self.assertEqual(details["items"][0]["batch_number"], "B-100")
        self.assertEqual(details["items"][0]["supplier"], "MedCo")

    def test_doctor_and_nurse_cannot_use_any_inventory_write_tool(self):
        calls = {
            "create_inventory_item": {"item_name": "X", "quantity": 1, "unit": "u"},
            "update_inventory_item": {"item_id": "inv-d5", "supplier": "Evil"},
            "adjust_inventory_stock": {"item_id": "inv-d5", "quantity_change": -40},
            "preview_inventory_import": {"text": "gloves 10 boxes"},
            "confirm_inventory_import": {"import_token": "t" * 32, "source_hash": "a" * 64,
                                         "rows": [{"row_id": "r", "action": "create", "item_name": "X", "quantity": 1, "unit": "u"}]},
        }
        self.assertEqual(set(calls), set(INVENTORY_WRITE_TOOLS))
        for uid in ("dem-x", "kav-x"):
            names = {t.name for t in registry.get_tools_for_role(ROLES[uid])}
            self.assertFalse(names & INVENTORY_WRITE_TOOLS, uid)
            for tool, args in calls.items():
                res = self.gw(uid, ROLES[uid], tool, args)
                self.assertEqual(res.get("error"), "FORBIDDEN", (uid, tool, res))
        self.assertEqual(self.count_items(), 8)
        self.assertEqual((self.item("inv-d5").current_stock, self.item("inv-d5").supplier), (40, "MedCo"))
        db = self.Session()
        self.assertEqual(db.query(models.AIPendingApproval).count(), 0)
        db.close()

    def test_owner_and_manager_create_with_duplicate_guard(self):
        for uid in ("own-x", "mgr-x"):
            res = self.gw(uid, ROLES[uid], "create_inventory_item",
                          {"item_name": f"Gauze {uid}", "quantity": 12, "unit": "packs", "expiry_date": d(100), "batch_number": "G1"})
            self.assertEqual(res.get("status"), "SUCCESS", res)
            self.assertTrue(res["persisted"])
            row = self.item(res["resource_id"])
            self.assertEqual((row.current_stock, row.unit, row.min_threshold, row.supplier), (12, "packs", 10, None))
        dup = self.gw("mgr-x", "INVENTORY_MANAGER", "create_inventory_item",
                      {"item_name": "nitrile gloves", "quantity": 1, "unit": "boxes", "expiry_date": d(5), "batch_number": "b-100"})
        self.assertIn("error", dup)
        self.assertIn("inv-d5", dup["detail"])
        bad = self.gw("mgr-x", "INVENTORY_MANAGER", "create_inventory_item",
                      {"item_name": "Thing", "quantity": 1, "unit": "u", "expiry_date": "next year"})
        self.assertIn("error", bad)
        self.assertEqual(self.count_items(), 10)

    def test_adjust_and_update_require_approval_then_persist(self):
        res = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock",
                      {"item_id": "inv-d5", "quantity_change": -15, "reason": "used in Room 101"})
        self.assertEqual(res["status"], "APPROVAL_REQUIRED")
        for text in ("Nitrile Gloves", "inv-d5", "Current quantity: 40 boxes", "Adjustment: -15 boxes", "New quantity after approval: 25 boxes"):
            self.assertIn(text, res["description"])
        self.assertEqual(self.item("inv-d5").current_stock, 40)
        approved = self.approve("mgr-x", res["approval_id"])
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "EXECUTED")
        self.assertEqual(self.item("inv-d5").current_stock, 25)

        upd = self.gw("own-x", "CLINIC_OWNER", "update_inventory_item", {"item_id": "inv-d5", "supplier": "NewCo", "min_threshold": 30})
        self.assertEqual(upd["status"], "APPROVAL_REQUIRED")
        self.assertIn("supplier: MedCo → NewCo", upd["description"])
        self.assertIn("min_threshold: 10 → 30", upd["description"])
        self.assertEqual(self.approve("own-x", upd["approval_id"]).json()["status"], "EXECUTED")
        item = self.item("inv-d5")
        self.assertEqual((item.supplier, item.min_threshold, item.current_stock), ("NewCo", 30, 25))

    def pending_approvals(self):
        db = self.Session()
        try:
            return db.query(models.AIPendingApproval).count()
        finally:
            db.close()

    def test_adjust_below_zero_is_refused_before_any_approval(self):
        res = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_id": "inv-d20", "quantity_change": -6})
        self.assertEqual(res.get("error"), "EXECUTION_ERROR", res)
        self.assertIn("only 5", res["detail"])
        self.assertEqual(self.pending_approvals(), 0)
        self.assertEqual(self.item("inv-d20").current_stock, 5)

    def test_cross_tenant_inventory_writes_and_reads_are_isolated(self):
        res = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_id": "inv-y", "quantity_change": -999})
        self.assertEqual(res.get("error"), "NOT_FOUND", res)
        self.assertEqual(self.pending_approvals(), 0)
        self.assertEqual(self.item("inv-y").current_stock, 999)
        # A tenant-y user cannot approve tenant-x's pending action
        res = self.gw("mgr-x", "INVENTORY_MANAGER", "adjust_inventory_stock", {"item_id": "inv-d5", "quantity_change": 1})
        self.assertNotEqual(self.approve("mgr-y", res["approval_id"], Y).status_code, 200)
        self.assertEqual(self.item("inv-d5").current_stock, 40)
        # A spoofed tenant_id argument is overwritten by the verified context
        y_view = self.gw("own-y", "CLINIC_OWNER", "get_inventory_status", {"search_query": "gloves", "tenant_id": T}, tenant=Y)
        self.assertEqual([i["item_id"] for i in y_view["items"]], ["inv-y"])

    def test_chat_import_preview_then_approved_confirmation(self):
        fake = FakeExtractionLLM(EXTRACTED)
        with mock.patch.object(inventory_service, "get_extraction_llm", return_value=(fake, "f")):
            preview = self.gw("mgr-x", "INVENTORY_MANAGER", "preview_inventory_import", {"text": "gauze 200 packs ..."})
        self.assertEqual(preview["status"], "SUCCESS")
        self.assertFalse(preview["persisted"])
        self.assertEqual(preview["rows_with_errors"], ["row-3"])
        self.assertEqual(self.count_items(), 8)
        args = preview["confirm_arguments"]
        args["rows"] = [r for r in args["rows"] if r["row_id"] != "row-3"]
        pending = self.gw("mgr-x", "INVENTORY_MANAGER", "confirm_inventory_import", args)
        self.assertEqual(pending["status"], "APPROVAL_REQUIRED")
        self.assertIn("CREATE Sterile Gauze Pads — 200 packs", pending["description"])
        self.assertIn("row-2: SKIP", pending["description"])
        self.assertEqual(self.count_items(), 8)
        out = self.approve("mgr-x", pending["approval_id"]).json()
        self.assertEqual(out["status"], "EXECUTED", out)
        self.assertIn("1 created", out["reply"])
        self.assertEqual(self.count_items(), 9)
        # Replaying the same approval cannot import twice
        self.assertNotEqual(self.approve("mgr-x", pending["approval_id"]).status_code, 200)
        self.assertEqual(self.count_items(), 9)


class InventoryAgentReadOnlyTests(Base):
    def run_agent(self, uid, message, fake=None, mode="gemini"):
        db = self.Session()
        try:
            if mode == "deterministic":
                return agent.run(message=message, conversation_history=[], context=self.ctx(uid, ROLES[uid]), db=db, agent_mode="deterministic")
            with mock.patch.object(agent_module, "get_gemini_llm", return_value=(fake, "fake-gemini")), \
                 mock.patch.dict(os.environ, {"GOOGLE_API_KEY": "test-only-not-a-key"}):
                return agent.run(message=message, conversation_history=[], context=self.ctx(uid, ROLES[uid]), db=db, agent_mode="gemini")
        finally:
            db.close()

    def test_read_only_question_never_executes_a_planned_inventory_write(self):
        rogue = AIMessage(content="", tool_calls=[
            {"name": "adjust_inventory_stock", "args": {"item_id": "inv-d5", "quantity_change": -40}, "id": "c1"},
            {"name": "create_inventory_item", "args": {"item_name": "Ghost", "quantity": 1, "unit": "u"}, "id": "c2"},
        ])
        fake = FakeGemini([rogue], "You have 40 boxes of Nitrile Gloves.")
        result = self.run_agent("mgr-x", "How many nitrile gloves do we have in stock?", fake)
        self.assertFalse(set(fake.bound_tool_names[0]) & INVENTORY_WRITE_TOOLS)
        self.assertIn("get_inventory_status", fake.bound_tool_names[0])
        self.assertEqual(self.item("inv-d5").current_stock, 40)
        self.assertEqual(self.count_items(), 8)
        self.assertEqual({t["tool"]: t["status"] for t in result["tool_calls_executed"]},
                         {"adjust_inventory_stock": "FAILED", "create_inventory_item": "FAILED"})
        self.assertIn("READ_ONLY_REQUEST", result["reply"])
        db = self.Session()
        self.assertEqual(db.query(models.AIPendingApproval).count(), 0)
        blocked = db.query(models.AIAuditEvent).filter_by(tenant_id=T, status="BLOCKED").all()
        db.close()
        self.assertEqual({b.tool_name for b in blocked}, {"adjust_inventory_stock", "create_inventory_item"})

    def test_deterministic_expiry_questions_read_real_data_for_every_role(self):
        for uid in ROLES:
            with mock.patch.object(inventory_service, "matches_expiry_filter", wraps=inventory_service.matches_expiry_filter) as spy:
                result = self.run_agent(uid, "Which items are expiring within 7 days?", mode="deterministic")
            tools = [t["tool"] for t in result["tool_calls_executed"]]
            self.assertEqual(tools, ["get_inventory_status"], (uid, tools))
            self.assertEqual({c.args[1] for c in spy.call_args_list}, {"within_7"})
            self.assertIn("Nitrile Gloves", result["reply"])
            self.assertIn("Today Gauze", result["reply"])
            for absent in ("Syringes 5ml", "Expired Saline", "Face Masks", "Tenant Y Gloves"):
                self.assertNotIn(absent, result["reply"], uid)
        self.assertEqual(self.count_items(), 8)

    def test_unverified_inventory_success_claim_is_replaced(self):
        fake = FakeGemini([AIMessage(content="The stock has been updated: Nitrile Gloves now at 80 boxes.")], "")
        result = self.run_agent("mgr-x", "Add 40 boxes of nitrile gloves to stock", fake)
        self.assertIn("PERSISTENCE_NOT_VERIFIED", result["reply"])
        self.assertEqual(self.item("inv-d5").current_stock, 40)

    def test_doctor_chat_never_sees_inventory_write_tools(self):
        fake = FakeGemini([], "Inventory is managed by Owners and Managers.")
        self.run_agent("dem-x", "Add 40 boxes of nitrile gloves to stock", fake)
        self.assertFalse(set(fake.bound_tool_names[0]) & INVENTORY_WRITE_TOOLS)


# =====================================================================================================
# Parts 4 & 5: task deletion lineage and Manager-to-Doctor reassignment
# =====================================================================================================

class TaskDeletionAndReassignmentTests(Base):
    def setUp(self):
        super().setUp()
        db = self.Session()
        db.add_all([
            _task("t-dem-nurse", "Dem created for nurse", "s-kav", "ATTENDING_PHYSICIAN", "dem-x"),
            _task("t-dem-self", "Dem created for self", "s-dem", "ATTENDING_PHYSICIAN", "dem-x"),
            _task("t-dem-open", "Dem created unassigned", None, "ATTENDING_PHYSICIAN", "dem-x"),
            _task("t-own-nurse", "Owner created for nurse", "s-kav", "CLINIC_OWNER", "own-x"),
            _task("t-mgr-nurse", "Manager created for nurse", "s-kav", "INVENTORY_MANAGER", "mgr-x"),
            _task("t-legacy", "Legacy nurse task", "s-kav"),
        ])
        db.commit()
        db.close()

    def flags(self, uid):
        return {t["id"]: t for t in self.client.get("/api/v1/tasks", headers=self.h(uid)).json()}

    def task(self, tid):
        db = self.Session()
        try:
            return db.query(models.Task).filter_by(id=tid).first()
        finally:
            db.close()

    def put(self, uid, tid, **fields):
        return self.client.put(f"/api/v1/tasks/{tid}", headers=self.h(uid), json=fields)

    def test_delete_flags_match_policy_for_doctors(self):
        dem, rac = self.flags("dem-x"), self.flags("rac-x")
        self.assertTrue(dem["t-dem-nurse"]["can_delete"])
        self.assertTrue(dem["t-dem-open"]["can_delete"])
        self.assertFalse(dem["t-dem-self"]["can_delete"])       # assigned to self
        self.assertFalse(dem["t-own-nurse"]["can_delete"])      # Owner-created
        self.assertFalse(dem["t-mgr-nurse"]["can_delete"])      # Manager-created
        self.assertFalse(dem["t-legacy"]["can_delete"])         # no recorded creator
        for tid in ("t-dem-nurse", "t-dem-open", "t-dem-self", "t-own-nurse", "t-legacy"):
            self.assertFalse(rac[tid]["can_delete"], tid)         # another Doctor's / not own

    def test_frontend_flag_matches_server_decision_for_every_task(self):
        for uid in ("dem-x", "rac-x"):
            for tid, t in self.flags(uid).items():
                code = self.client.delete(f"/api/v1/tasks/{tid}", headers=self.h(uid)).status_code
                self.assertEqual(code == 204, t["can_delete"], (uid, tid, code))
                if code == 204:
                    self.setUp()  # restore fixture for the remaining checks

    def test_doctor_task_reassigned_to_nurse_becomes_deletable_and_keeps_lineage(self):
        self.assertEqual(self.client.delete("/api/v1/tasks/t-dem-self", headers=self.h("dem-x")).status_code, 403)
        res = self.put("dem-x", "t-dem-self", title="Dem created for self (edited)", assigned_staff_id="s-kav")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["can_delete"])
        row = self.task("t-dem-self")
        self.assertEqual((row.created_by_user_id, row.created_by_role), ("dem-x", "ATTENDING_PHYSICIAN"))
        self.assertFalse(self.flags("rac-x")["t-dem-self"]["can_delete"])
        self.assertEqual(self.client.delete("/api/v1/tasks/t-dem-self", headers=self.h("rac-x")).status_code, 403)
        self.assertEqual(self.client.delete("/api/v1/tasks/t-dem-self", headers=self.h("dem-x")).status_code, 204)

    def test_editing_a_nurse_task_keeps_delete_permission(self):
        res = self.put("dem-x", "t-dem-nurse", title="Renamed", priority="High", assigned_staff_id="s-kav", status="In Progress")
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json()["can_delete"])
        self.assertTrue(self.flags("dem-x")["t-dem-nurse"]["can_delete"])

    def test_manager_reassigning_doctor_task_to_another_doctor_removes_doctor_delete(self):
        self.assertEqual(self.put("mgr-x", "t-dem-nurse", assigned_staff_id="s-rac").status_code, 200)
        self.assertFalse(self.flags("dem-x")["t-dem-nurse"]["can_delete"])  # now another Doctor's work
        self.assertFalse(self.flags("rac-x")["t-dem-nurse"]["can_delete"])  # assigned to self, not creator
        self.assertEqual(self.task("t-dem-nurse").created_by_user_id, "dem-x")

    def test_doctor_delete_api_rejections_are_server_side(self):
        for tid in ("t-dem-self", "t-own-nurse", "t-mgr-nurse", "t-legacy"):
            self.assertEqual(self.client.delete(f"/api/v1/tasks/{tid}", headers=self.h("dem-x")).status_code, 403, tid)
            self.assertIsNotNone(self.task(tid))
        self.assertEqual(self.client.delete("/api/v1/tasks/t-dem-nurse", headers=self.h("rac-x")).status_code, 403)
        db = self.Session()
        res = gateway.execute("delete_clinical_task", {"task_id": "t-own-nurse"}, self.ctx("dem-x", "ATTENDING_PHYSICIAN"), db)
        db.close()
        self.assertIn("error", res)
        self.assertIsNotNone(self.task("t-own-nurse"))

    def test_manager_to_doctor_reassignment_keeps_task_visible_everywhere(self):
        created = self.client.post("/api/v1/tasks", headers=self.h("mgr-x"),
                                   json={"title": "Delegated by manager", "due_date": "2026-10-21", "assigned_staff_id": "s-kav"}).json()
        tid = created["id"]
        res = self.put("mgr-x", tid, title="Delegated by manager", description="", priority="Medium", status="Pending",
                       due_date="2026-10-21", assigned_staff_id="s-dem", room_id=None)
        self.assertEqual(res.status_code, 200, res.text)
        row = self.task(tid)
        self.assertEqual((row.assigned_staff_id, row.created_by_user_id, row.created_by_role), ("s-dem", "mgr-x", "INVENTORY_MANAGER"))

        mgr = self.flags("mgr-x")
        self.assertIn(tid, mgr)
        self.assertTrue(mgr[tid]["can_edit"])
        dem = self.flags("dem-x")
        self.assertIn(tid, dem)
        self.assertTrue(dem[tid]["can_complete"])
        self.assertFalse(dem[tid]["can_delete"])
        self.assertEqual(self.client.get(f"/api/v1/tasks/{tid}", headers=self.h("dem-x")).status_code, 200)

        for uid in ("mgr-x", "dem-x"):
            summary = self.client.get("/api/v1/dashboard/summary", headers=self.h(uid)).json()
            self.assertEqual(summary["tasks_total"], len(self.flags(uid)), uid)
        ai = self.gw("dem-x", "ATTENDING_PHYSICIAN", "list_tasks", {})
        self.assertIn(tid, [t["task_id"] for t in ai["tasks"]])

        self.assertEqual(self.client.delete(f"/api/v1/tasks/{tid}", headers=self.h("dem-x")).status_code, 403)
        self.assertEqual(self.put("dem-x", tid, status="Completed").status_code, 200)
        self.assertEqual(self.task(tid).status, "Completed")
        self.assertEqual(self.task(tid).created_by_role, "INVENTORY_MANAGER")

    def test_doctor_staff_label_does_not_override_verified_role(self):
        db = self.Session()
        db.query(models.Staff).filter_by(id="s-rac").update({"role": "Admin"})
        db.commit()
        db.close()
        self.assertEqual(self.put("mgr-x", "t-mgr-nurse", assigned_staff_id="s-rac").status_code, 200)
        self.assertIn("t-mgr-nurse", self.flags("dem-x"))
        self.assertIn("t-mgr-nurse", self.flags("rac-x"))

    def test_ai_task_list_limit_applies_after_visibility(self):
        db = self.Session()
        db.add_all([_task(f"t-hidden-{i:02d}", "Owner private", None, "CLINIC_OWNER", "own-x", due="2026-01-01") for i in range(25)])
        db.commit()
        db.close()
        ai = self.gw("dem-x", "ATTENDING_PHYSICIAN", "list_tasks", {})
        ids = [t["task_id"] for t in ai["tasks"]]
        self.assertIn("t-dem-nurse", ids)
        self.assertFalse([i for i in ids if i.startswith("t-hidden")])

    def test_owner_and_nurse_behaviour_unchanged(self):
        own = self.flags("own-x")
        self.assertTrue(all(t["can_delete"] for t in own.values()))
        self.assertEqual(self.client.delete("/api/v1/tasks/t-legacy", headers=self.h("own-x")).status_code, 204)
        self.assertEqual(self.client.delete("/api/v1/tasks/t-dem-nurse", headers=self.h("mgr-x")).status_code, 204)
        self.assertEqual(self.client.delete("/api/v1/tasks/t-dem-self", headers=self.h("mgr-x")).status_code, 204)
        kav = self.flags("kav-x")
        self.assertTrue(all(not t["can_delete"] for t in kav.values()))
        self.assertTrue(kav["t-own-nurse"]["can_complete"])
        self.assertEqual(self.client.delete("/api/v1/tasks/t-own-nurse", headers=self.h("kav-x")).status_code, 403)
        self.assertEqual(self.put("kav-x", "t-own-nurse", status="Completed").status_code, 200)
        self.assertEqual(self.put("kav-x", "t-own-nurse", title="nope").status_code, 403)


if __name__ == "__main__":
    unittest.main()
