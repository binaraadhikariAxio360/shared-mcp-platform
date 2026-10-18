import json
import urllib.request
import urllib.error

def req(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {}
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("x-tenant-id", "tenant-001")
    headers.setdefault("x-user-id", "test-broker-user")
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
    print("=== PROPSIGHTS REAL ESTATE POSTGRESQL CRUD & COPILOT TEST SUITE ===\n")
    base = "http://localhost:5003"

    # 1. Health & Database Check
    s, data = req(f"{base}/health")
    assert s == 200, f"Health check failed with status {s}: {data}"
    assert data.get("database_connected") is True, f"Database not connected: {data}"
    print(f"1. Health Check: OK (DB Connected: {data.get('database_connected')}, Service: {data.get('service')})")

    # 2. Dashboard Analytics & Summary Verification
    s, summary = req(f"{base}/api/v1/dashboard/summary")
    assert s == 200, f"Dashboard summary failed: {summary}"
    assert summary["active_listings_count"] >= 0, f"Invalid active listings count: {summary}"
    assert summary["under_contract_volume"] >= 0, f"Invalid under contract volume: {summary}"
    print(
        f"2. Dashboard Summary: OK (Active Listings: {summary['active_listings_count']}, "
        f"Under Contract Vol: ${summary['under_contract_volume']:,.2f}, "
        f"High Affinity Buyers: {summary['matched_buyers_count']}, "
        f"Avg Deal Size: ${summary['average_deal_size']:,.2f})"
    )

    # 3. Property Listings CRUD Lifecycle
    s, properties = req(f"{base}/api/v1/properties")
    assert s == 200 and isinstance(properties, list), f"List properties failed: {properties}"
    initial_prop_count = len(properties)
    print(f"3a. List Properties: OK ({initial_prop_count} properties found)")

    # Filterable check
    s, avail_props = req(f"{base}/api/v1/properties?status=AVAILABLE")
    assert s == 200 and all(p["status"] == "AVAILABLE" for p in avail_props), "Filtered properties failed"
    print(f"3b. Filter Properties: OK ({len(avail_props)} AVAILABLE properties)")

    # Create Property
    s, new_prop = req(f"{base}/api/v1/properties", "POST", {
        "title": "Zilker Park Contemporary Villa",
        "address": "1420 Barton Springs Rd, Austin, TX 78704",
        "price": 1650000.0,
        "beds": 4,
        "baths": 3.5,
        "sqft": 3400,
        "amenities": ["Infinity Pool", "Wine Cellar", "Solar Roof", "Smart Automation"],
        "assigned_agent": "Elena Vance"
    })
    assert s == 201 and new_prop["title"] == "Zilker Park Contemporary Villa", f"Create property failed: {new_prop}"
    prop_id = new_prop["id"]
    print(f"3c. Create Property: OK (Created ID {prop_id}, Price: ${new_prop['price']:,})")

    # Update Property (Price & Status switch)
    s, updated_prop = req(f"{base}/api/v1/properties/{prop_id}", "PUT", {
        "status": "UNDER_CONTRACT",
        "price": 1625000.0
    })
    assert s == 200 and updated_prop["status"] == "UNDER_CONTRACT" and updated_prop["price"] == 1625000.0, f"Update property failed: {updated_prop}"
    print(f"3d. Update Property: OK (Status: {updated_prop['status']}, Price: ${updated_prop['price']:,})")

    # Delete Property
    s, _ = req(f"{base}/api/v1/properties/{prop_id}", "DELETE")
    assert s == 204, f"Delete property failed with status {s}"
    s, post_del_prop = req(f"{base}/api/v1/properties/{prop_id}")
    assert s == 404, "Property record still exists after deletion!"
    print(f"3e. Delete Property: OK (Successfully deleted {prop_id})")

    # 4. Prospective Buyers CRUD Lifecycle
    s, buyers = req(f"{base}/api/v1/buyers")
    assert s == 200 and isinstance(buyers, list), f"List buyers failed: {buyers}"
    initial_buyer_count = len(buyers)
    print(f"4a. List Buyers: OK ({initial_buyer_count} prospective buyers found)")

    # Filter buyers by preapproval
    s, preapproved_buyers = req(f"{base}/api/v1/buyers?preapproved_only=true")
    assert s == 200 and all(b["is_preapproved"] for b in preapproved_buyers), "Filter preapproved buyers failed"
    print(f"4b. Filter Buyers: OK ({len(preapproved_buyers)} pre-approved buyers)")

    # Create Buyer
    s, new_buyer = req(f"{base}/api/v1/buyers", "POST", {
        "name": "Marcus & Rachel Sterling",
        "budget": 1750000.0,
        "preferred_type": "Single Family",
        "target_area": "Zilker / South Austin",
        "is_preapproved": True,
        "affinity_score": 92
    })
    assert s == 201 and new_buyer["name"] == "Marcus & Rachel Sterling", f"Create buyer failed: {new_buyer}"
    buyer_id = new_buyer["id"]
    print(f"4c. Create Buyer: OK (Created ID {buyer_id}, Budget: ${new_buyer['budget']:,})")

    # Update Buyer
    s, updated_buyer = req(f"{base}/api/v1/buyers/{buyer_id}", "PUT", {
        "budget": 1800000.0,
        "affinity_score": 96
    })
    assert s == 200 and updated_buyer["budget"] == 1800000.0 and updated_buyer["affinity_score"] == 96, f"Update buyer failed: {updated_buyer}"
    print(f"4d. Update Buyer: OK (New Budget: ${updated_buyer['budget']:,}, Affinity: {updated_buyer['affinity_score']}%)")

    # Delete Buyer
    s, _ = req(f"{base}/api/v1/buyers/{buyer_id}", "DELETE")
    assert s == 204, f"Delete buyer failed with status {s}"
    s, post_del_buyer = req(f"{base}/api/v1/buyers/{buyer_id}")
    assert s == 404, "Buyer record still exists after deletion!"
    print(f"4e. Delete Buyer: OK (Successfully deleted {buyer_id})")

    # 5. Deal Contracts CRUD Lifecycle
    s, deals = req(f"{base}/api/v1/deals")
    assert s == 200 and isinstance(deals, list), f"List deals failed: {deals}"
    print(f"5a. List Deals: OK ({len(deals)} escrow deals found)")

    # Create Deal
    first_prop = properties[0]["id"] if properties else "prp-001"
    first_buyer = buyers[0]["id"] if buyers else "byr-001"
    s, new_deal = req(f"{base}/api/v1/deals", "POST", {
        "property_id": first_prop,
        "buyer_id": first_buyer,
        "contract_price": 865000.0,
        "closing_date": "2026-11-28",
        "stage": "OFFER",
        "commission_rate": 0.03
    })
    assert s == 201 and new_deal["stage"] == "OFFER", f"Create deal failed: {new_deal}"
    deal_id = new_deal["id"]
    print(f"5b. Create Deal: OK (Created ID {deal_id}, Price: ${new_deal['contract_price']:,}, Stage: {new_deal['stage']})")

    # Update Deal (Transition stage to UNDER_CONTRACT)
    s, updated_deal = req(f"{base}/api/v1/deals/{deal_id}", "PUT", {
        "stage": "UNDER_CONTRACT",
        "contract_price": 870000.0
    })
    assert s == 200 and updated_deal["stage"] == "UNDER_CONTRACT", f"Update deal failed: {updated_deal}"
    print(f"5c. Update Deal: OK (Stage transitioned to {updated_deal['stage']})")

    # Delete Deal
    s, _ = req(f"{base}/api/v1/deals/{deal_id}", "DELETE")
    assert s == 204, f"Delete deal failed with status {s}"
    s, post_del_deal = req(f"{base}/api/v1/deals/{deal_id}")
    assert s == 404, "Deal record still exists after deletion!"
    print(f"5d. Delete Deal: OK (Successfully deleted {deal_id})")

    # 6. Agents Roster Check & Creation
    s, agents = req(f"{base}/api/v1/agents")
    assert s == 200 and len(agents) > 0, f"List agents failed: {agents}"
    print(f"6a. List Agents: OK ({len(agents)} active agents in roster)")

    s, new_agent = req(f"{base}/api/v1/agents", "POST", {
        "name": "Julian Montgomery",
        "email": "julian@austinpremier.com",
        "phone": "(512) 555-0199",
        "license_no": "TX-TREC-789123",
        "active_listings_count": 3
    })
    assert s == 201 and new_agent["name"] == "Julian Montgomery", f"Create agent failed: {new_agent}"
    print(f"6b. Create Agent: OK (Added Agent {new_agent['name']}, License: {new_agent['license_no']})")

    # 7. Internal AI Copilot Tools (Direct PostgreSQL Queries)
    # 7a. propsights.list_properties
    s, tool_props = req(f"{base}/internal/tools/propsights.list_properties", "POST", {"status": "AVAILABLE"})
    assert s == 200 and "properties" in tool_props, f"AI list_properties failed: {tool_props}"
    print(f"7a. AI Tool 'propsights.list_properties': OK ({tool_props['count']} properties returned)")

    # 7b. propsights.match_buyers
    s, match_res = req(f"{base}/internal/tools/propsights.match_buyers", "POST", {"min_affinity": 90})
    assert s == 200 and "matches" in match_res, f"AI match_buyers failed: {match_res}"
    match_count = match_res.get("match_count", len(match_res.get("matches", [])))
    print(f"7b. AI Tool 'propsights.match_buyers': OK ({match_count} matches found, Top match: {match_res['matches'][0]['buyer_name'] if match_res['matches'] else 'N/A'})")

    # 7c. propsights.get_pipeline_summary
    s, pipe_res = req(f"{base}/internal/tools/propsights.get_pipeline_summary", "POST", {})
    assert s == 200 and "pipeline_volume" in pipe_res and "deals" in pipe_res, f"AI get_pipeline_summary failed: {pipe_res}"
    print(f"7c. AI Tool 'propsights.get_pipeline_summary': OK (Escrow Volume: ${pipe_res['under_contract_volume']:,.2f}, Total Deals: {pipe_res['total_deals_count']})")

    print("\n========================================================")
    print(" ALL PROPSIGHTS POSTGRESQL CRUD & AI COPILOT TESTS PASSED!")
    print("========================================================\n")

if __name__ == "__main__":
    run_tests()
