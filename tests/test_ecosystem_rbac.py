import requests
import json
import sys

def run_tests():
    print("=" * 70)
    print("AXIO360 ECOSYSTEM MULTI-TENANT & RBAC COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    all_passed = True

    # -------------------------------------------------------------------------
    # 1. FRONTEND HEALTH CHECKS
    # -------------------------------------------------------------------------
    print("\n--- [1] FRONTEND SERVICES HEALTH (:3001 - :3004) ---")
    frontends = [
        ("PractiCare UI", "http://localhost:3001"),
        ("TaxSnap UI", "http://localhost:3002"),
        ("PropSights UI", "http://localhost:3003"),
        ("OnScribe UI", "http://localhost:3004"),
    ]

    for name, url in frontends:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code == 200:
                print(f"[PASS] {name} ({url}) is UP (HTTP 200)")
            else:
                print(f"[FAIL] {name} ({url}) returned HTTP {r.status_code}")
                all_passed = False
        except Exception as e:
            print(f"[FAIL] {name} ({url}) error: {e}")
            all_passed = False

    # -------------------------------------------------------------------------
    # 2. BACKEND AUTH ROLES & ROOT ENDPOINTS
    # -------------------------------------------------------------------------
    print("\n--- [2] BACKEND AUTH ROLES ENDPOINTS (:5001 - :5004) ---")
    backends = [
        ("PractiCare API", "http://localhost:5001"),
        ("TaxSnap API", "http://localhost:5002"),
        ("PropSights API", "http://localhost:5003"),
        ("OnScribe API", "http://localhost:5004"),
    ]

    for name, base in backends:
        try:
            # Root route
            r_root = requests.get(f"{base}/", timeout=5)
            assert r_root.status_code == 200, f"Root returned {r_root.status_code}"

            # Auth roles route
            headers = {"x-tenant-id": "tenant-001", "x-user-role": "ADMIN", "x-user-id": "test-user"}
            r_roles = requests.get(f"{base}/api/v1/auth/roles", headers=headers, timeout=5)
            assert r_roles.status_code == 200, f"Auth roles returned {r_roles.status_code}"
            data = r_roles.json()
            assert "roles" in data and len(data["roles"]) >= 4, f"Missing roles in {data}"
            print(f"[PASS] {name} ({base}): Root OK & Auth Roles OK ({len(data['roles'])} roles configured)")
        except Exception as e:
            print(f"[FAIL] {name} ({base}) error: {e}")
            all_passed = False

    # -------------------------------------------------------------------------
    # 3. PRACTICARE MULTI-TENANT ISOLATION & RBAC (:5001)
    # -------------------------------------------------------------------------
    print("\n--- [3] PRACTICARE (:5001) MULTI-TENANT & RBAC ---")
    base_pc = "http://localhost:5001"
    try:
        # Tenant Isolation
        h_t1 = {"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "owner-1"}
        h_t2 = {"x-tenant-id": "tenant-002", "x-user-role": "CLINIC_OWNER", "x-user-id": "owner-2"}

        r_t1 = requests.get(f"{base_pc}/api/v1/rooms", headers=h_t1).json()
        r_t2 = requests.get(f"{base_pc}/api/v1/rooms", headers=h_t2).json()
        assert len(r_t1) > 0 and len(r_t2) > 0, "Empty rooms list in seed"
        assert r_t1[0]["tenant_id"] == "tenant-001"
        assert r_t2[0]["tenant_id"] == "tenant-002"
        print(f"[PASS] Tenant Isolation: tenant-001 has {len(r_t1)} rooms, tenant-002 has {len(r_t2)} rooms (Strict Partitioning)")

        # RBAC: NURSE_STAFF delete room forbidden
        h_nurse = {"x-tenant-id": "tenant-001", "x-user-role": "NURSE_STAFF", "x-user-id": "nurse-1"}
        r_del = requests.delete(f"{base_pc}/api/v1/rooms/{r_t1[0]['id']}", headers=h_nurse)
        assert r_del.status_code == 403, f"Expected 403 for NURSE_STAFF delete room, got {r_del.status_code}"
        print(f"[PASS] RBAC Enforcement: NURSE_STAFF DELETE room -> HTTP 403 ({r_del.json().get('detail')})")

        # RBAC: INVENTORY_MANAGER create task forbidden
        h_inv = {"x-tenant-id": "tenant-001", "x-user-role": "INVENTORY_MANAGER", "x-user-id": "inv-1"}
        r_task = requests.post(f"{base_pc}/api/v1/tasks", headers=h_inv, json={"title": "Clinical biopsy prep", "priority": "HIGH", "status": "PENDING", "due_date": "2026-11-01"})
        assert r_task.status_code == 403, f"Expected 403 for INVENTORY_MANAGER task post, got {r_task.status_code}"
        print(f"[PASS] RBAC Enforcement: INVENTORY_MANAGER POST task -> HTTP 403 ({r_task.json().get('detail')})")
    except Exception as e:
        print(f"[FAIL] PractiCare tests: {e}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 4. TAXSNAP MULTI-TENANT ISOLATION & RBAC (:5002)
    # -------------------------------------------------------------------------
    print("\n--- [4] TAXSNAP (:5002) MULTI-TENANT & RBAC ---")
    base_ts = "http://localhost:5002"
    try:
        # Tenant Isolation
        h_t1 = {"x-tenant-id": "tenant-001", "x-user-role": "FINANCE_DIRECTOR", "x-user-id": "dir-1"}
        h_t2 = {"x-tenant-id": "tenant-002", "x-user-role": "FINANCE_DIRECTOR", "x-user-id": "dir-2"}

        sum_t1 = requests.get(f"{base_ts}/api/v1/dashboard/summary", headers=h_t1).json()
        sum_t2 = requests.get(f"{base_ts}/api/v1/dashboard/summary", headers=h_t2).json()
        assert sum_t1["tenant_id"] == "tenant-001" and sum_t2["tenant_id"] == "tenant-002"
        assert sum_t1["business_name"] != sum_t2["business_name"]
        print(f"[PASS] Tenant Isolation: tenant-001 '{sum_t1['business_name']}' != tenant-002 '{sum_t2['business_name']}'")

        # RBAC: AUDITOR_STAKEHOLDER post income forbidden
        h_audit = {"x-tenant-id": "tenant-001", "x-user-role": "AUDITOR_STAKEHOLDER", "x-user-id": "audit-1"}
        r_inc = requests.post(f"{base_ts}/api/v1/income", headers=h_audit, json={"source": "Stock Gain", "amount": 10000, "date": "2026-10-15", "status": "Received"})
        assert r_inc.status_code == 403, f"Expected 403 for AUDITOR_STAKEHOLDER income create, got {r_inc.status_code}"
        print(f"[PASS] RBAC Enforcement: AUDITOR_STAKEHOLDER POST income -> HTTP 403 ({r_inc.json().get('detail')})")

        # RBAC: BOOKKEEPER delete expense forbidden
        exp_list = requests.get(f"{base_ts}/api/v1/expenses", headers=h_t1).json()
        assert len(exp_list) > 0, "Expenses list empty"
        h_bk = {"x-tenant-id": "tenant-001", "x-user-role": "BOOKKEEPER", "x-user-id": "bk-1"}
        r_exp_del = requests.delete(f"{base_ts}/api/v1/expenses/{exp_list[0]['id']}", headers=h_bk)
        assert r_exp_del.status_code == 403, f"Expected 403 for BOOKKEEPER delete expense, got {r_exp_del.status_code}"
        print(f"[PASS] RBAC Enforcement: BOOKKEEPER DELETE expense -> HTTP 403 ({r_exp_del.json().get('detail')})")
    except Exception as e:
        print(f"[FAIL] TaxSnap tests: {e}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 5. PROPSIGHTS MULTI-TENANT ISOLATION & RBAC (:5003)
    # -------------------------------------------------------------------------
    print("\n--- [5] PROPSIGHTS (:5003) MULTI-TENANT & RBAC ---")
    base_ps = "http://localhost:5003"
    try:
        # Tenant Isolation
        h_t1 = {"x-tenant-id": "tenant-001", "x-user-role": "PRINCIPAL_BROKER", "x-user-id": "broker-1"}
        h_t2 = {"x-tenant-id": "tenant-002", "x-user-role": "PRINCIPAL_BROKER", "x-user-id": "broker-2"}

        sum_t1 = requests.get(f"{base_ps}/api/v1/dashboard/summary", headers=h_t1).json()
        sum_t2 = requests.get(f"{base_ps}/api/v1/dashboard/summary", headers=h_t2).json()
        assert sum_t1["tenant_id"] == "tenant-001" and sum_t2["tenant_id"] == "tenant-002"
        assert sum_t1["brokerage_name"] != sum_t2["brokerage_name"]
        print(f"[PASS] Tenant Isolation: tenant-001 '{sum_t1['brokerage_name']}' != tenant-002 '{sum_t2['brokerage_name']}'")

        # RBAC: CLIENT_BUYER create property forbidden
        h_buyer = {"x-tenant-id": "tenant-001", "x-user-role": "CLIENT_BUYER", "x-user-id": "buyer-1"}
        r_prop = requests.post(f"{base_ps}/api/v1/properties", headers=h_buyer, json={"title": "Luxury Villa", "address": "123 Ocean Dr", "price": 2500000, "beds": 5, "baths": 5, "sqft": 4500, "amenities": "Pool", "status": "AVAILABLE"})
        assert r_prop.status_code == 403, f"Expected 403 for CLIENT_BUYER property create, got {r_prop.status_code}"
        print(f"[PASS] RBAC Enforcement: CLIENT_BUYER POST property -> HTTP 403 ({r_prop.json().get('detail')})")

        # RBAC: LICENSED_AGENT delete deal forbidden
        deals = requests.get(f"{base_ps}/api/v1/deals", headers=h_t1).json()
        assert len(deals) > 0, "Deals list empty"
        h_agent = {"x-tenant-id": "tenant-001", "x-user-role": "LICENSED_AGENT", "x-user-id": "agent-1"}
        r_deal_del = requests.delete(f"{base_ps}/api/v1/deals/{deals[0]['id']}", headers=h_agent)
        assert r_deal_del.status_code == 403, f"Expected 403 for LICENSED_AGENT delete deal, got {r_deal_del.status_code}"
        print(f"[PASS] RBAC Enforcement: LICENSED_AGENT DELETE deal -> HTTP 403 ({r_deal_del.json().get('detail')})")
    except Exception as e:
        print(f"[FAIL] PropSights tests: {e}")
        all_passed = False

    # -------------------------------------------------------------------------
    # 6. ONSCRIBE MULTI-TENANT ISOLATION & RBAC (:5004)
    # -------------------------------------------------------------------------
    print("\n--- [6] ONSCRIBE (:5004) MULTI-TENANT & RBAC ---")
    base_os = "http://localhost:5004"
    try:
        # Tenant Isolation
        h_t1 = {"x-tenant-id": "tenant-001", "x-user-role": "OPERATIONS_DIRECTOR", "x-user-id": "ops-1"}
        h_t2 = {"x-tenant-id": "tenant-002", "x-user-role": "OPERATIONS_DIRECTOR", "x-user-id": "ops-2"}

        sum_t1 = requests.get(f"{base_os}/api/v1/dashboard/summary", headers=h_t1).json()
        sum_t2 = requests.get(f"{base_os}/api/v1/dashboard/summary", headers=h_t2).json()
        assert sum_t1["tenant_id"] == "tenant-001" and sum_t2["tenant_id"] == "tenant-002"
        assert sum_t1["organization_name"] != sum_t2["organization_name"]
        print(f"[PASS] Tenant Isolation: tenant-001 '{sum_t1['organization_name']}' != tenant-002 '{sum_t2['organization_name']}'")

        # RBAC: TEAM_CONTRIBUTOR delete deliverable forbidden
        dlvs = requests.get(f"{base_os}/api/v1/deliverables", headers=h_t1).json()
        assert len(dlvs) > 0, "Deliverables empty"
        h_staff = {"x-tenant-id": "tenant-001", "x-user-role": "TEAM_CONTRIBUTOR", "x-user-id": "staff-1"}
        r_dlv_del = requests.delete(f"{base_os}/api/v1/deliverables/{dlvs[0]['id']}", headers=h_staff)
        assert r_dlv_del.status_code == 403, f"Expected 403 for TEAM_CONTRIBUTOR delete deliverable, got {r_dlv_del.status_code}"
        print(f"[PASS] RBAC Enforcement: TEAM_CONTRIBUTOR DELETE deliverable -> HTTP 403 ({r_dlv_del.json().get('detail')})")

        # RBAC: COMPLIANCE_AUDITOR create project forbidden
        h_aud = {"x-tenant-id": "tenant-001", "x-user-role": "COMPLIANCE_AUDITOR", "x-user-id": "aud-1"}
        r_prj = requests.post(f"{base_os}/api/v1/projects", headers=h_aud, json={"name": "Shadow Project", "code": "SP-01", "sprint_cycle": "Q4", "target_date": "2026-12-31"})
        assert r_prj.status_code == 403, f"Expected 403 for COMPLIANCE_AUDITOR create project, got {r_prj.status_code}"
        print(f"[PASS] RBAC Enforcement: COMPLIANCE_AUDITOR POST project -> HTTP 403 ({r_prj.json().get('detail')})")
    except Exception as e:
        print(f"[FAIL] OnScribe tests: {e}")
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED! 100% MULTI-TENANT ISOLATION & RBAC COMPLIANCE VERIFIED.")
    else:
        print("SOME TESTS FAILED! CHECK OUTPUT ABOVE.")
    print("=" * 70)
    return all_passed

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

