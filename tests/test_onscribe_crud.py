import json
import urllib.request
import urllib.error

def req(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("x-tenant-id", "tenant-001")
    headers.setdefault("x-user-id", "test-ops-director")
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
    print("=== ONSCRIBE OPERATIONS & COMPLIANCE POSTGRESQL CRUD TEST SUITE ===\n")
    base = "http://localhost:5004"

    # 1. Health & Database Check
    s, data = req(f"{base}/health")
    assert s == 200, f"Health check failed with status {s}: {data}"
    assert data.get("database_connected") is True, f"Database not connected: {data}"
    print(f"1. Health Check: OK (DB Connected: {data.get('database_connected')}, Service: {data.get('service')})")

    # 2. Dashboard Summary Verification
    s, summary = req(f"{base}/api/v1/dashboard/summary")
    assert s == 200, f"Dashboard summary failed: {summary}"
    assert summary["active_projects_count"] > 0, f"Expected active projects > 0, got {summary['active_projects_count']}"
    assert summary["overdue_tasks_count"] >= 0, f"Expected overdue tasks >= 0, got {summary['overdue_tasks_count']}"
    assert summary["compliance_audited_count"] >= 18, f"Expected compliance docs >= 18, got {summary['compliance_audited_count']}"
    print(
        f"2. Dashboard Summary: OK (Active Projects: {summary['active_projects_count']}, "
        f"Overdue Tasks: {summary['overdue_tasks_count']} [{summary['critical_overdue_count']} Critical], "
        f"Overburdened Staff: {summary['overburdened_staff_count']}, "
        f"SLA Escalation: {summary['sla_escalation_status']})"
    )

    # 3. Deliverables CRUD Lifecycle
    s, deliverables = req(f"{base}/api/v1/deliverables")
    assert s == 200 and isinstance(deliverables, list), f"List deliverables failed: {deliverables}"
    initial_dlv_count = len(deliverables)
    print(f"3a. List Deliverables: OK ({initial_dlv_count} deliverables found)")

    # Filter deliverables by priority
    s, crit_deliverables = req(f"{base}/api/v1/deliverables?priority=CRITICAL")
    assert s == 200 and all(d["priority"] == "CRITICAL" for d in crit_deliverables), "Filtered deliverables failed"
    print(f"3b. Filter Deliverables: OK ({len(crit_deliverables)} CRITICAL deliverables)")

    # Create Deliverable
    s, new_dlv = req(f"{base}/api/v1/deliverables", "POST", {
        "title": "Automated Multi-Region Disaster Recovery Drill",
        "project_id": "prj-iso-27k",
        "assignee_id": "tm-devon-01",
        "priority": "CRITICAL",
        "status": "IN_PROGRESS",
        "due_date": "2026-11-20",
        "sla_days_overdue": 0
    })
    assert s == 201 and new_dlv["title"] == "Automated Multi-Region Disaster Recovery Drill", f"Create deliverable failed: {new_dlv}"
    dlv_id = new_dlv["id"]
    print(f"3c. Create Deliverable: OK (Created ID {dlv_id}, Priority: {new_dlv['priority']})")

    # Update Deliverable (Toggle status to COMPLETED)
    s, updated_dlv = req(f"{base}/api/v1/deliverables/{dlv_id}", "PUT", {
        "status": "COMPLETED"
    })
    assert s == 200 and updated_dlv["status"] == "COMPLETED", f"Update deliverable failed: {updated_dlv}"
    print(f"3d. Update Deliverable: OK (Status marked as {updated_dlv['status']})")

    # Delete Deliverable
    s, _ = req(f"{base}/api/v1/deliverables/{dlv_id}", "DELETE")
    assert s == 204, f"Delete deliverable failed with status {s}"
    s, post_del_dlv = req(f"{base}/api/v1/deliverables/{dlv_id}")
    assert s == 404, "Deliverable still exists after deletion!"
    print(f"3e. Delete Deliverable: OK (Successfully deleted {dlv_id})")

    # 4. Sprint Projects CRUD Lifecycle
    s, projects = req(f"{base}/api/v1/projects")
    assert s == 200 and isinstance(projects, list), f"List projects failed: {projects}"
    print(f"4a. List Projects: OK ({len(projects)} sprint projects found)")

    # Create Project
    s, new_prj = req(f"{base}/api/v1/projects", "POST", {
        "name": "Zero-Trust Service Mesh Migration",
        "code": "ZTS-MESH",
        "status": "ACTIVE",
        "sprint_cycle": "Sprint 25-Q1",
        "target_date": "2026-12-31"
    })
    assert s == 201 and new_prj["code"] == "ZTS-MESH", f"Create project failed: {new_prj}"
    prj_id = new_prj["id"]
    print(f"4b. Create Project: OK (Created ID {prj_id}, Code: {new_prj['code']})")

    # Update Project
    s, updated_prj = req(f"{base}/api/v1/projects/{prj_id}", "PUT", {
        "status": "ON_HOLD",
        "sprint_cycle": "Sprint 25-Q2"
    })
    assert s == 200 and updated_prj["status"] == "ON_HOLD", f"Update project failed: {updated_prj}"
    print(f"4c. Update Project: OK (Status updated to {updated_prj['status']})")

    # Delete Project
    s, _ = req(f"{base}/api/v1/projects/{prj_id}", "DELETE")
    assert s == 204, f"Delete project failed with status {s}"
    s, post_del_prj = req(f"{base}/api/v1/projects/{prj_id}")
    assert s == 404, "Project still exists after deletion!"
    print(f"4d. Delete Project: OK (Successfully deleted {prj_id})")

    # 5. Team Members CRUD Lifecycle
    s, team = req(f"{base}/api/v1/team")
    assert s == 200 and len(team) > 0, f"List team failed: {team}"
    print(f"5a. List Team: OK ({len(team)} members in roster)")

    # Create Team Member
    s, new_tm = req(f"{base}/api/v1/team", "POST", {
        "name": "Evelyn Harper",
        "role": "Governance & Risk Manager",
        "email": "evelyn.harper@apexops.internal",
        "max_task_threshold": 4
    })
    assert s == 201 and new_tm["name"] == "Evelyn Harper", f"Create team member failed: {new_tm}"
    tm_id = new_tm["id"]
    print(f"5b. Create Team Member: OK (Created ID {tm_id}, Role: {new_tm['role']})")

    # Update Team Member
    s, updated_tm = req(f"{base}/api/v1/team/{tm_id}", "PUT", {
        "max_task_threshold": 5
    })
    assert s == 200 and updated_tm["max_task_threshold"] == 5, f"Update team member failed: {updated_tm}"
    print(f"5c. Update Team Member: OK (Max threshold adjusted to {updated_tm['max_task_threshold']})")

    # Delete Team Member
    s, _ = req(f"{base}/api/v1/team/{tm_id}", "DELETE")
    assert s == 204, f"Delete team member failed with status {s}"
    s, post_del_tm = req(f"{base}/api/v1/team/{tm_id}")
    assert s == 404, "Team member still exists after deletion!"
    print(f"5d. Delete Team Member: OK (Successfully deleted {tm_id})")

    # 6. Compliance Documents CRUD Lifecycle
    s, compliance = req(f"{base}/api/v1/compliance")
    assert s == 200 and len(compliance) >= 18, f"List compliance failed: {compliance}"
    print(f"6a. List Compliance Docs: OK ({len(compliance)} documents registered)")

    # Create Compliance Document
    s, new_doc = req(f"{base}/api/v1/compliance", "POST", {
        "title": "FedRAMP Moderate Cloud Security Architecture Audit",
        "standard": "FedRAMP",
        "status": "IN_REVIEW",
        "audit_date": "2026-11-05",
        "auditor_name": "Coalfire Systems"
    })
    assert s == 201 and new_doc["title"] == "FedRAMP Moderate Cloud Security Architecture Audit", f"Create compliance failed: {new_doc}"
    doc_id = new_doc["id"]
    print(f"6b. Create Compliance Doc: OK (Created ID {doc_id}, Standard: {new_doc['standard']})")

    # Update Compliance Document
    s, updated_doc = req(f"{base}/api/v1/compliance/{doc_id}", "PUT", {
        "status": "AUDITED"
    })
    assert s == 200 and updated_doc["status"] == "AUDITED", f"Update compliance failed: {updated_doc}"
    print(f"6c. Update Compliance Doc: OK (Status changed to {updated_doc['status']})")

    # Delete Compliance Document
    s, _ = req(f"{base}/api/v1/compliance/{doc_id}", "DELETE")
    assert s == 204, f"Delete compliance doc failed with status {s}"
    s, post_del_doc = req(f"{base}/api/v1/compliance/{doc_id}")
    assert s == 404, "Compliance doc still exists after deletion!"
    print(f"6d. Delete Compliance Doc: OK (Successfully deleted {doc_id})")

    # 7. Live AI Copilot Tools (Direct PostgreSQL Queries)
    # 7a. onscribe.list_overdue_tasks
    s, overdue_res = req(f"{base}/internal/tools/onscribe.list_overdue_tasks", "POST", {})
    assert s == 200 and "tasks" in overdue_res and overdue_res["count"] >= 0, f"AI list_overdue_tasks failed: {overdue_res}"
    print(f"7a. AI Tool 'onscribe.list_overdue_tasks': OK ({overdue_res['count']} overdue tasks, {overdue_res['critical_count']} critical)")

    # 7b. onscribe.analyze_team_workload
    s, workload_res = req(f"{base}/internal/tools/onscribe.analyze_team_workload", "POST", {})
    assert s == 200 and "team" in workload_res and workload_res["member_count"] > 0, f"AI analyze_team_workload failed: {workload_res}"
    print(f"7b. AI Tool 'onscribe.analyze_team_workload': OK ({workload_res['member_count']} members audited, {workload_res['overburdened_count']} overburdened)")

    # 7c. onscribe.get_operations_summary
    s, ops_summary = req(f"{base}/internal/tools/onscribe.get_operations_summary", "POST", {})
    assert s == 200 and "sla_risk_level" in ops_summary and "deliverables_summary" in ops_summary, f"AI get_operations_summary failed: {ops_summary}"
    print(f"7c. AI Tool 'onscribe.get_operations_summary': OK (SLA Risk: {ops_summary['sla_risk_level']}, Active Projects: {ops_summary['active_projects']})")

    print("\n========================================================")
    print(" ALL ONSCRIBE POSTGRESQL CRUD & AI COPILOT TESTS PASSED!")
    print("========================================================\n")

if __name__ == "__main__":
    run_tests()
