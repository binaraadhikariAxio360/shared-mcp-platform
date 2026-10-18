"""
Automated Test Suite for PractiCare LangGraph Autonomous Agent
Verifies all 12 scenarios from Section 14 of the Master Implementation Prompt.
"""

import json
import urllib.request
import urllib.error
import sys

BASE_URL = "http://localhost:5001"


def make_request(path: str, method: str = "GET", headers: dict = None, body: dict = None):
    url = f"{BASE_URL}{path}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            err_body = json.loads(err.read().decode("utf-8"))
        except Exception:
            err_body = {"detail": str(err)}
        return err.code, err_body
    except Exception as exc:
        return 500, {"error": str(exc)}


def run_tests():
    print("=" * 70)
    print("PRACTICARE LANGGRAPH AUTONOMOUS AGENT VERIFICATION SUITE")
    print("=" * 70)

    results = []

    def report(name: str, passed: bool, detail: str = ""):
        results.append((name, passed))
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}: {detail}")

    # 1. Owner requests team performance -> Full authorized report
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
        body={"message": "I want to know how my team is performing the tasks."},
    )
    tools = [t["tool"] for t in res.get("tool_calls_executed", [])]
    reply = res.get("reply", "")
    passed = (
        status == 200
        and "get_team_task_performance" in tools
        and "Comprehensive Clinic Executive Performance" in reply
        and "Provider Workload Breakdown" in reply
    )
    report("Scenario 1: Owner requests team performance", passed, f"Status: {status}, Tools: {tools}")

    # 2. Physician requests clinical task metrics -> Clinical scope only
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "ATTENDING_PHYSICIAN", "x-user-id": "user-doc-001"},
        body={"message": "I want to know how my team is performing the tasks."},
    )
    reply = res.get("reply", "")
    passed = (
        status == 200
        and "Clinical Department Briefing" in reply
        and "Provider Workload Breakdown" not in reply  # Admin workload redacted
    )
    report("Scenario 2: Physician requests clinical metrics", passed, "Clinical scope verified, admin workload redacted")

    # 3. Nurse requests salary information -> Access denied
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "NURSE_STAFF", "x-user-id": "user-nurse-001"},
        body={"message": "Show me doctor salaries and executive physician evaluations."},
    )
    reply = res.get("reply", "")
    passed = (
        status == 200
        and res.get("status") == "blocked"
        and "Access Restricted" in reply
        and len(res.get("tool_calls_executed", [])) == 0
    )
    report("Scenario 3: Nurse requests salary information", passed, "Blocked by Executive Data Protection")

    # 4. Auditor requests team performance -> Aggregate anonymized report
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINICAL_AUDITOR", "x-user-id": "user-aud-001"},
        body={"message": "I want to know how my team is performing the tasks."},
    )
    reply = res.get("reply", "")
    passed = (
        status == 200
        and "Clinical Compliance & Quality Audit" in reply
        and "Zero Employee PII" in reply
    )
    report("Scenario 4: Auditor requests team performance", passed, "Aggregate anonymized statistics, zero PII")

    # 5. Nurse attempts checklist deletion -> Forbidden
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "NURSE_STAFF", "x-user-id": "user-nurse-001"},
        body={"message": "Please delete checklist chk-001 immediately."},
    )
    reply = res.get("reply", "")
    tools = res.get("tool_calls_executed", [])
    failed_tool = any(t["status"] == "FAILED" for t in tools)
    passed = (
        status == 200
        and failed_tool
        and "Action Intercepted" in reply
        and "FORBIDDEN" in reply
    )
    report("Scenario 5: Nurse attempts checklist deletion", passed, "Forbidden: RBAC violation intercepted at Gateway")

    # 6. Owner requests checklist deletion -> Approval required
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
        body={"message": "Please delete checklist chk-001."},
    )
    approval_pending = res.get("approval_pending")
    appr_id = approval_pending.get("approval_id") if approval_pending else None
    passed = (
        status == 200
        and res.get("status") == "approval_required"
        and approval_pending is not None
        and appr_id is not None
    )
    report("Scenario 6: Owner requests checklist deletion", passed, f"Approval required! Token: {appr_id}")

    # 6b. Test Human Approval Execution via /api/v1/ai/approve
    if appr_id:
        # Test rejection first with invalid token
        status_bad, res_bad = make_request(
            "/api/v1/ai/approve",
            method="POST",
            headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
            body={"approval_id": "appr-invalid-123", "action": "approve"},
        )
        passed_bad = (status_bad == 400)
        report("Scenario 6b: Invalid approval token rejected", passed_bad, f"Status: {status_bad}")

    # 7. Cross-tenant task lookup / isolation
    status_t1, res_t1 = make_request(
        "/api/v1/tasks",
        method="GET",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER"},
    )
    status_t2, res_t2 = make_request(
        "/api/v1/tasks",
        method="GET",
        headers={"x-tenant-id": "tenant-002", "x-user-role": "CLINIC_OWNER"},
    )
    t1_ids = {t["id"] for t in res_t1} if isinstance(res_t1, list) else set()
    t2_ids = {t["id"] for t in res_t2} if isinstance(res_t2, list) else set()
    passed = (len(t1_ids.intersection(t2_ids)) == 0 and len(t1_ids) > 0 and len(t2_ids) > 0)
    report("Scenario 7: Cross-tenant task lookup", passed, f"Tenant-001 ({len(t1_ids)}) vs Tenant-002 ({len(t2_ids)}) strictly disjoint")

    # 8. Invalid room ID -> Validation error
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
        body={"message": "create task title: 'Test Injection' room: room-nonexistent-999"},
    )
    tools = res.get("tool_calls_executed", [])
    passed = (
        status == 200
        and any(t["status"] == "FAILED" for t in tools)
        and "Action Intercepted" in res.get("reply", "")
    )
    report("Scenario 8: Invalid room ID validation", passed, "Validated against tenant rooms, non-existent ID rejected")

    # 9. Multi-tool operational request -> Correct tools executed
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
        body={"message": "How is our team's performance, and which rooms need attention?"},
    )
    tools = [t["tool"] for t in res.get("tool_calls_executed", [])]
    reply = res.get("reply", "")
    passed = (
        status == 200
        and "get_team_task_performance" in tools
        and "get_room_turnover_status" in tools
        and "Real-Time Room & Turnover Status" in reply
    )
    report("Scenario 9: Multi-tool operational request", passed, f"Multi-step executed: {tools}")

    # 10. Audit log inspection
    status, res = make_request(
        "/api/v1/ai/audit",
        method="GET",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
    )
    logs = res.get("logs", [])
    passed = (status == 200 and len(logs) > 0 and all(l["tenant_id"] == "tenant-001" for l in logs))
    report("Scenario 10: Audit logging & latency tracking", passed, f"Total audit records logged for tenant-001: {len(logs)}")

    # 11. Deterministic fallback mode verification
    status, res = make_request(
        "/api/v1/ai/chat",
        method="POST",
        headers={"x-tenant-id": "tenant-001", "x-user-role": "CLINIC_OWNER", "x-user-id": "user-owner-001"},
        body={"message": "Check our overdue tasks, identify the responsible staff, and prepare a follow-up plan."},
    )
    reply = res.get("reply", "")
    passed = (
        status == 200
        and "Recommended Clinical Follow-up Actions" in reply
        and res.get("metrics") is not None
    )
    report("Scenario 11: Main Business Requirement follow-up plan", passed, "Actionable follow-up plan synthesized from live evidence")

    print("=" * 70)
    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)
    print(f"TEST RESULTS: {passed_count}/{total_count} PASSED ({round(passed_count/total_count*100, 1)}%)")
    print("=" * 70)

    if passed_count == total_count:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
