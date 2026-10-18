import json
import urllib.request
import urllib.error

def req(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("x-tenant-id", "tenant-001")
    headers.setdefault("x-user-id", "test-cpa-user")
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request) as resp:
            code = resp.status
            content = resp.read().decode("utf-8")
            return code, json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        return e.code, json.loads(content) if content else {}

def run_tests():
    print("=== TAXSNAP POSTGRESQL CRUD & COMPLIANCE TEST SUITE ===\n")
    base = "http://localhost:5002"

    # 1. Health & Database Check
    s, data = req(f"{base}/health")
    assert s == 200, f"Health check failed with status {s}: {data}"
    assert data.get("database_connected") is True, f"Database not connected: {data}"
    print(f"1. Health Check: OK (DB Connected: {data.get('database_connected')}, Service: {data.get('service')})")

    # 2. Tax Profile Check
    s, prof = req(f"{base}/api/v1/profile")
    assert s == 200 and prof.get("business_name") is not None, f"Get profile failed: {prof}"
    print(f"2a. Profile Check: OK (Entity: '{prof['business_name']}', TIN: {prof['tin_number']}, Tax Rate: {prof['corporate_tax_rate']})")

    # Update profile
    s, updated_prof = req(f"{base}/api/v1/profile", "PUT", {"corporate_tax_rate": 0.21})
    assert s == 200 and updated_prof["corporate_tax_rate"] == 0.21, f"Update profile failed: {updated_prof}"
    print(f"2b. Profile Update: OK (Rate set to {updated_prof['corporate_tax_rate']})")

    # 3. Dashboard Analytics & Summary Verification
    s, summary = req(f"{base}/api/v1/dashboard/summary")
    assert s == 200, f"Dashboard summary failed: {summary}"
    assert summary["gross_income"] > 0, f"Expected gross income > 0, got {summary['gross_income']}"
    assert summary["total_expenses"] > 0, f"Expected total expenses > 0, got {summary['total_expenses']}"
    assert summary["net_taxable_income"] >= 0, f"Invalid net taxable income: {summary['net_taxable_income']}"
    print(
        f"3. Dashboard Summary: OK (Gross: ${summary['gross_income']:,}, "
        f"Deductible Exp: ${summary['total_deductible_expenses']:,}, "
        f"Taxable: ${summary['net_taxable_income']:,}, "
        f"Est Tax Liability: ${summary['estimated_tax_liability']:,})"
    )

    # 4. Income CRUD Lifecycle
    s, incomes = req(f"{base}/api/v1/income")
    assert s == 200 and len(incomes) > 0, f"List income failed: {incomes}"
    initial_inc_count = len(incomes)
    print(f"4a. List Income: OK ({initial_inc_count} records found)")

    # Create Income
    s, new_inc = req(f"{base}/api/v1/income", "POST", {
        "source": "Automated Advisory Retainer Test Q4",
        "amount": 50000.0,
        "date": "2026-10-18",
        "status": "Received"
    })
    assert s == 201 and new_inc["source"] == "Automated Advisory Retainer Test Q4", f"Create income failed: {new_inc}"
    inc_id = new_inc["id"]
    print(f"4b. Create Income: OK (Created ID {inc_id}, Amount: ${new_inc['amount']:,})")

    # Update Income
    s, updated_inc = req(f"{base}/api/v1/income/{inc_id}", "PUT", {
        "status": "Invoiced",
        "amount": 55000.0
    })
    assert s == 200 and updated_inc["status"] == "Invoiced" and updated_inc["amount"] == 55000.0, f"Update income failed: {updated_inc}"
    print(f"4c. Update Income: OK (Status: {updated_inc['status']}, Amount: ${updated_inc['amount']:,})")

    # Delete Income
    s, _ = req(f"{base}/api/v1/income/{inc_id}", "DELETE")
    assert s == 204, f"Delete income failed with status {s}"
    s, post_del_inc = req(f"{base}/api/v1/income/{inc_id}")
    assert s == 404, "Income record still exists after deletion!"
    print(f"4d. Delete Income: OK (Successfully deleted {inc_id})")

    # 5. Expense CRUD Lifecycle
    s, expenses = req(f"{base}/api/v1/expenses")
    assert s == 200 and len(expenses) > 0, f"List expenses failed: {expenses}"
    initial_exp_count = len(expenses)
    print(f"5a. List Expenses: OK ({initial_exp_count} records found)")

    # Create Expense
    s, new_exp = req(f"{base}/api/v1/expenses", "POST", {
        "vendor": "NVIDIA DGX Cloud Compute Cluster",
        "category": "Cloud Infrastructure",
        "amount": 18200.0,
        "is_deductible": True,
        "date": "2026-10-12",
        "receipt_url": "https://receipts.corp/nvidia-dgx.pdf"
    })
    assert s == 201 and new_exp["vendor"] == "NVIDIA DGX Cloud Compute Cluster", f"Create expense failed: {new_exp}"
    exp_id = new_exp["id"]
    print(f"5b. Create Expense: OK (Created ID {exp_id}, Vendor: '{new_exp['vendor']}', Deductible: {new_exp['is_deductible']})")

    # Update Expense (toggle deductible)
    s, updated_exp = req(f"{base}/api/v1/expenses/{exp_id}", "PUT", {
        "is_deductible": False,
        "amount": 19000.0
    })
    assert s == 200 and updated_exp["is_deductible"] is False, f"Update expense failed: {updated_exp}"
    print(f"5c. Update Expense: OK (Toggled deductible to False, Amount: ${updated_exp['amount']:,})")

    # Delete Expense
    s, _ = req(f"{base}/api/v1/expenses/{exp_id}", "DELETE")
    assert s == 204, f"Delete expense failed with status {s}"
    s, post_del_exp = req(f"{base}/api/v1/expenses/{exp_id}")
    assert s == 404, "Expense record still exists after deletion!"
    print(f"5d. Delete Expense: OK (Successfully deleted {exp_id})")

    # 6. Tax Document CRUD Lifecycle
    s, docs = req(f"{base}/api/v1/documents")
    assert s == 200 and len(docs) > 0, f"List documents failed: {docs}"
    initial_doc_count = len(docs)
    print(f"6a. List Tax Documents: OK ({initial_doc_count} documents found)")

    # Create Document
    s, new_doc = req(f"{base}/api/v1/documents", "POST", {
        "document_type": "Form 5471 Foreign Corporation Information Return",
        "status": "PENDING_UPLOAD",
        "deadline": "2026-11-30",
        "assigned_cpa": "Elena Rostova, CPA"
    })
    assert s == 201 and new_doc["document_type"] == "Form 5471 Foreign Corporation Information Return", f"Create doc failed: {new_doc}"
    doc_id = new_doc["id"]
    print(f"6b. Create Tax Document: OK (Created ID {doc_id}, Type: '{new_doc['document_type']}')")

    # Update Document (verify status)
    s, updated_doc = req(f"{base}/api/v1/documents/{doc_id}", "PUT", {
        "status": "VERIFIED"
    })
    assert s == 200 and updated_doc["status"] == "VERIFIED", f"Update doc failed: {updated_doc}"
    print(f"6c. Update Tax Document: OK (Marked as VERIFIED)")

    # Delete Document
    s, _ = req(f"{base}/api/v1/documents/{doc_id}", "DELETE")
    assert s == 204, f"Delete doc failed with status {s}"
    s, post_del_doc = req(f"{base}/api/v1/documents/{doc_id}")
    assert s == 404, "Document record still exists after deletion!"
    print(f"6d. Delete Tax Document: OK (Successfully deleted {doc_id})")

    # 7. AI Copilot Tools Verification
    # Tool 1: taxsnap.get_tax_summary
    s, tool_tax = req(f"{base}/internal/tools/taxsnap.get_tax_summary", "POST", {})
    assert s == 200 and tool_tax.get("estimated_tax_liability") is not None, f"Tool get_tax_summary failed: {tool_tax}"
    print(f"7a. AI Tool 'taxsnap.get_tax_summary': OK (Gross: ${tool_tax['gross_income']:,}, Est Liability: ${tool_tax['estimated_tax_liability']:,})")

    # Tool 2: taxsnap.list_expenses
    s, tool_exp = req(f"{base}/internal/tools/taxsnap.list_expenses", "POST", {"only_deductible": True})
    assert s == 200 and tool_exp.get("count") > 0, f"Tool list_expenses failed: {tool_exp}"
    print(f"7b. AI Tool 'taxsnap.list_expenses': OK ({tool_exp['count']} deductible records, Total: ${tool_exp['total_amount']:,})")

    # Tool 3: taxsnap.list_missing_documents
    s, tool_docs = req(f"{base}/internal/tools/taxsnap.list_missing_documents", "POST", {})
    assert s == 200 and tool_docs.get("count") is not None, f"Tool list_missing_documents failed: {tool_docs}"
    print(f"7c. AI Tool 'taxsnap.list_missing_documents': OK ({tool_docs['count']} pending/missing compliance filings)")

    print("\n>>> ALL TESTS PASSED! TAXSNAP FULL-STACK POSTGRESQL SUITE IS FULLY OPERATIONAL! <<<\n")

if __name__ == "__main__":
    run_tests()
