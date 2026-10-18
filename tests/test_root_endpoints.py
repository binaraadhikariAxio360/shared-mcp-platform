import json
import urllib.request
import urllib.error

def check_url(url, timeout=3):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Axio360-Root-Auditor/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            content = resp.read().decode("utf-8")
            try:
                data = json.loads(content)
            except Exception:
                data = content[:100]
            return code, data
    except urllib.error.HTTPError as e:
        content = e.read().decode("utf-8")
        try:
            data = json.loads(content)
        except Exception:
            data = content[:100]
        return e.code, data
    except Exception as e:
        return 0, str(e)

def run_verification():
    print("=================================================================", flush=True)
    print("   AXIO360 ECOSYSTEM ROOT & HEALTH ENDPOINTS AUDIT", flush=True)
    print("=================================================================\n", flush=True)

    services = [
        {"name": "PractiCare", "backend": "http://127.0.0.1:5001", "frontend": "http://127.0.0.1:3001"},
        {"name": "TaxSnap",    "backend": "http://127.0.0.1:5002", "frontend": "http://127.0.0.1:3002"},
        {"name": "PropSights", "backend": "http://127.0.0.1:5003", "frontend": "http://127.0.0.1:3003"},
        {"name": "OnScribe",   "backend": "http://127.0.0.1:5004", "frontend": "http://127.0.0.1:3004"},
    ]

    all_passed = True

    # 1. Audit Backend Root URLs
    print("--- 1. BACKEND ROOT INDEX ENDPOINTS ('/') ---", flush=True)
    for s in services:
        url = f"{s['backend']}/"
        status, data = check_url(url)
        if status == 200 and isinstance(data, dict) and data.get("status") == "operational":
            print(f" [PASS] {s['name']:11} -> {url:26} [HTTP {status}] Service: '{data.get('service')}' | DB: '{data.get('database')}'", flush=True)
        else:
            all_passed = False
            print(f" [FAIL] {s['name']:11} -> {url:26} [HTTP {status}] Body: {data}", flush=True)

    # 2. Audit Backend Health URLs
    print("\n--- 2. BACKEND HEALTH ENDPOINTS ('/health') ---", flush=True)
    for s in services:
        url = f"{s['backend']}/health"
        status, data = check_url(url)
        if status == 200 and isinstance(data, dict) and data.get("database_connected") is True:
            print(f" [PASS] {s['name']:11} -> {url:26} [HTTP {status}] DB Connected: {data.get('database_connected')}", flush=True)
        else:
            all_passed = False
            print(f" [FAIL] {s['name']:11} -> {url:26} [HTTP {status}] Body: {data}", flush=True)

    # 3. Audit Frontend URLs
    print("\n--- 3. FRONTEND PORTAL ENDPOINTS ---", flush=True)
    for s in services:
        url = s['frontend']
        status, data = check_url(url)
        if status == 200:
            print(f" [PASS] {s['name']:11} -> {url:26} [HTTP {status}] UI Online", flush=True)
        else:
            all_passed = False
            print(f" [FAIL] {s['name']:11} -> {url:26} [HTTP {status}] Error: {data}", flush=True)

    print("\n=================================================================", flush=True)
    if all_passed:
        print(" [SUCCESS] ALL 4 ROOT URLS, HEALTH ENDPOINTS & FRONTENDS 100% OPERATIONAL!", flush=True)
    else:
        print(" [FAILURE] SOME ENDPOINTS FAILED VERIFICATION.", flush=True)
    print("=================================================================\n", flush=True)

    return all_passed

if __name__ == "__main__":
    success = run_verification()
    exit(0 if success else 1)
