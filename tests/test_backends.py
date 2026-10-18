import json
import urllib.request
import urllib.error

def request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    headers.setdefault("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))

def test_all():
    print("=== AXIO360 BACKENDS VERIFICATION SUITE ===\n")
    headers = {"x-tenant-id": "tenant-001", "x-user-id": "tester-1"}

    # 1. PractiCare
    print("--- 1. PractiCare Backend (Port 5001) ---")
    s, res = request("http://localhost:5001/health")
    assert s == 200, f"PractiCare health check failed: {res}"
    print(f"Health: {res['status']} ({res['service']})")

    s, res = request("http://localhost:5001/internal/tools/practicare.list_tasks", "POST", {}, headers)
    assert s == 200 and res["total_count"] > 0, f"list_tasks failed: {res}"
    print(f"list_tasks: {res['total_count']} tasks found for {res['tenant_id']}")

    s, res = request("http://localhost:5001/internal/tools/practicare.get_low_stock", "POST", {}, headers)
    assert s == 200 and res["alert_count"] > 0, f"get_low_stock failed: {res}"
    print(f"get_low_stock: {res['alert_count']} low stock alerts found")

    s, res = request("http://localhost:5001/internal/tools/practicare.get_practice_summary", "POST", {}, headers)
    assert s == 200, f"get_practice_summary failed: {res}"
    print(f"get_practice_summary: clinic '{res['practice_name']}' has {res['total_rooms']} rooms and {res['active_staff_count']} staff")

    # 2. TaxSnap
    print("\n--- 2. TaxSnap Backend (Port 5002) ---")
    s, res = request("http://localhost:5002/health")
    assert s == 200, f"TaxSnap health check failed: {res}"
    print(f"Health: {res['status']} ({res['service']})")

    s, res = request("http://localhost:5002/internal/tools/taxsnap.get_tax_summary", "POST", {}, headers)
    assert s == 200, f"get_tax_summary failed: {res}"
    print(f"get_tax_summary: Income=${res['total_income']:,.2f}, Deductible Expenses=${res['total_deductible_expenses']:,.2f}, Est. Tax Liability=${res['estimated_tax_liability']:,.2f}")

    s, res = request("http://localhost:5002/internal/tools/taxsnap.list_expenses", "POST", {"deductible_only": True}, headers)
    assert s == 200 and res["total_count"] > 0, f"list_expenses failed: {res}"
    print(f"list_expenses: {res['total_count']} deductible expenses totaling ${res['total_amount']:,.2f}")

    s, res = request("http://localhost:5002/internal/tools/taxsnap.list_missing_documents", "POST", {}, headers)
    assert s == 200 and res["pending_count"] > 0, f"list_missing_documents failed: {res}"
    print(f"list_missing_documents: {res['pending_count']} pending/missing documents")

    # 3. PropSights
    print("\n--- 3. PropSights Backend (Port 5003) ---")
    s, res = request("http://localhost:5003/health")
    assert s == 200, f"PropSights health check failed: {res}"
    print(f"Health: {res['status']} ({res['service']})")

    s, res = request("http://localhost:5003/internal/tools/propsights.search_properties", "POST", {"property_type": "Condo"}, headers)
    assert s == 200 and res["result_count"] > 0, f"search_properties failed: {res}"
    print(f"search_properties: {res['result_count']} matching condos found")
    sample_prop_id = res["properties"][0]["id"]

    s, res = request("http://localhost:5003/internal/tools/propsights.get_listing", "POST", {"property_id": sample_prop_id}, headers)
    assert s == 200, f"get_listing failed: {res}"
    print(f"get_listing: {res['property']['title']} (${res['property']['price']:,.2f}) - Agent: {res['assigned_agent']}")

    s, res = request("http://localhost:5003/internal/tools/propsights.match_buyer", "POST", {}, headers)
    assert s == 200 and res["total_matches"] > 0, f"match_buyer failed: {res}"
    print(f"match_buyer: matched {res['total_matches']} listing matches across prospective buyers")

    # 4. OnScribe
    print("\n--- 4. OnScribe Backend (Port 5004) ---")
    s, res = request("http://localhost:5004/health")
    assert s == 200, f"OnScribe health check failed: {res}"
    print(f"Health: {res['status']} ({res['service']})")

    s, res = request("http://localhost:5004/internal/tools/onscribe.list_overdue_tasks", "POST", {}, headers)
    assert s == 200 and res["overdue_count"] > 0, f"list_overdue_tasks failed: {res}"
    print(f"list_overdue_tasks: {res['overdue_count']} overdue operational tasks identified")

    s, res = request("http://localhost:5004/internal/tools/onscribe.get_team_workload", "POST", {"overburden_threshold": 4}, headers)
    assert s == 200 and res["team_size"] > 0, f"get_team_workload failed: {res}"
    print(f"get_team_workload: {res['team_size']} members, {res['overburdened_members_count']} overburdened (Avg tasks: {res['average_tasks_per_member']})")

    s, res = request("http://localhost:5004/internal/tools/onscribe.search_documents", "POST", {"query": "security"}, headers)
    assert s == 200 and res["total_found"] > 0, f"search_documents failed: {res}"
    print(f"search_documents: {res['total_found']} documents matched query 'security'")

    # Multi-tenant test
    print("\n--- 5. Multi-Tenant Isolation Verification ---")
    mt_headers = {"x-tenant-id": "tenant-custom-99", "x-user-id": "isolated-user"}
    s, res = request("http://localhost:5001/internal/tools/practicare.list_tasks", "POST", {}, mt_headers)
    assert s == 200 and res["tenant_id"] == "tenant-custom-99", "Multi-tenancy failed for PractiCare"
    print(f"Isolated tenant 'tenant-custom-99' successfully isolated and seeded in PractiCare: {res['total_count']} task(s)")

    s, res = request("http://localhost:5002/internal/tools/taxsnap.get_tax_summary", "POST", {}, mt_headers)
    assert s == 200 and res["tenant_id"] == "tenant-custom-99", "Multi-tenancy failed for TaxSnap"
    print(f"Isolated tenant 'tenant-custom-99' successfully isolated in TaxSnap: Profile '{res['business_name']}'")

    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! ALL 4 BACKENDS OPERATIONAL! <<<")

if __name__ == "__main__":
    test_all()
