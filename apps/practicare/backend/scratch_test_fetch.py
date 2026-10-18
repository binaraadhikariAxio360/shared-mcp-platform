import urllib.request
import json

def login_and_fetch(email, password="password123"):
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            token = data["access_token"]
            user = data["user"]
            print(f"=== LOGIN SUCCESS: {user['name']} ({user['role']}) tenant={user['tenant_id']} ===")
    except Exception as e:
        print(f"=== LOGIN FAILED for {email}: {e} ===")
        return

    # Fetch Tasks
    treq = urllib.request.Request("http://localhost:8000/api/v1/tasks", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(treq) as resp:
        tasks = json.loads(resp.read().decode())
        print(f"TASKS: count={len(tasks)}")
        for t in tasks:
            print(f"   task: id={t['id']} title='{t['title']}' status={t['status']} staff={t.get('assigned_staff_name')} role={t.get('created_by_role')}")

    # Fetch Checklists
    creq = urllib.request.Request("http://localhost:8000/api/v1/checklists", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(creq) as resp:
        chks = json.loads(resp.read().decode())
        print(f"CHECKLISTS: count={len(chks)}")
        for c in chks:
            print(f"   chk: id={c['id']} title='{c['title']}' completed={c['is_completed']} staff={c.get('assigned_staff_name')}")

print("--- Test 1: tenant-001 Owner ---")
login_and_fetch("owner@vanguardclinic.com")

print("\n--- Test 2: tenant-002 Owner ---")
login_and_fetch("owner@metrohealth.com")

print("\n--- Test 3: tenant-easternwav-cd6b Owner (direct token) ---")
from security import create_access_token
token_binara = create_access_token("usr-7a899030", "tenant-easternwav-cd6b", "CLINIC_OWNER")
treq = urllib.request.Request("http://localhost:8000/api/v1/tasks", headers={"Authorization": f"Bearer {token_binara}"})
with urllib.request.urlopen(treq) as resp:
    tasks = json.loads(resp.read().decode())
    print(f"TASKS (tenant-easternwav-cd6b): count={len(tasks)}")
    for t in tasks:
        print(f"   task: id={t['id']} title='{t['title']}' status={t['status']} staff={t.get('assigned_staff_name')}")

creq = urllib.request.Request("http://localhost:8000/api/v1/checklists", headers={"Authorization": f"Bearer {token_binara}"})
with urllib.request.urlopen(creq) as resp:
    chks = json.loads(resp.read().decode())
    print(f"CHECKLISTS (tenant-easternwav-cd6b): count={len(chks)}")
    for c in chks:
        print(f"   chk: id={c['id']} title='{c['title']}' completed={c['is_completed']} staff={c.get('assigned_staff_name')}")

