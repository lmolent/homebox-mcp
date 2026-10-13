# /// script
# dependencies = ["fastmcp", "httpx"]
# ///
"""Automated end-to-end verification of all Homebox MCP tools."""
import os
import sys

# Load environment variables from .env if present
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

if not os.getenv("HOMEBOX_API_KEY"):
    sys.exit("ERROR: HOMEBOX_API_KEY is not set. Please set it in .env or environment.")

import homebox_mcp as m

def run_tests():
    print("=== 1. Testing get_statistics() ===")
    stats = m.get_statistics()
    print("Stats:", stats)
    assert "totalItems" in stats
    assert "totalLocations" in stats

    print("\n=== 2. Testing list_locations() ===")
    locs = m.list_locations()
    print(f"Found {len(locs)} locations.")
    assert len(locs) > 0
    first_loc = locs[0]
    print(f"Sample location: {first_loc['name']} (ID: {first_loc['id']}, Path: {first_loc['full_path']})")

    print("\n=== 3. Testing search_items() with query & parent_ids ===")
    jeep_loc = next((l for l in locs if "Jeep" in l["name"]), None)
    if jeep_loc:
        jeep_items = m.search_items(parent_ids=[jeep_loc["id"]])
        print(f"Items in {jeep_loc['name']}: {[it['name'] for it in jeep_items.get('items', [])]}")
        assert jeep_items.get("total", 0) > 0

    print("\n=== 4. Testing get_item_by_asset_id() & get_item_path() ===")
    asset_res = m.get_item_by_asset_id("000-015")
    items = asset_res.get("items", [])
    assert len(items) > 0
    item_id = items[0]["id"]
    print(f"Found asset 000-015: {items[0]['name']} (ID: {item_id})")
    
    path = m.get_item_path(item_id)
    print("Path breadcrumbs:", " > ".join(p["name"] for p in path))
    assert len(path) >= 1

    print("\n=== 5. Testing create_location() ===")
    new_loc = m.create_location(name="Test MCP Dielna", description="Docasna testovacia lokacia")
    loc_id = new_loc["id"]
    print(f"Created location: {new_loc['name']} (ID: {loc_id})")

    try:
        print("\n=== 6. Testing create_item() with metadata ===")
        new_item = m.create_item(
            name="Testovaci Skrutkovac",
            description="Aku skrutkovac 18V",
            parent_id=loc_id,
            quantity=1,
            serial_number="SN-TEST-9988",
            model_number="MOD-18V-PRO",
            manufacturer="Bosch",
            notes="Overovaci test pre MCP",
            purchase_price=129.99
        )
        test_item_id = new_item["id"]
        print(f"Created item: {new_item['name']} (ID: {test_item_id})")
        assert new_item.get("serialNumber") == "SN-TEST-9988"
        assert new_item.get("manufacturer") == "Bosch"

        print("\n=== 7. Testing update_item() (safe PUT merge) ===")
        updated = m.update_item(test_item_id, {
            "description": "Aktualizovany popis skrutkovaca",
            "quantity": 2,
            "notes": "Poznamka uspesne aktualizovana"
        })
        print(f"Updated description: {updated.get('description')}, quantity: {updated.get('quantity')}")
        assert updated.get("description") == "Aktualizovany popis skrutkovaca"
        assert updated.get("quantity") == 2
        assert updated.get("serialNumber") == "SN-TEST-9988"  # Preserved!

        print("\n=== 8. Testing move_item() ===")
        # Move into root (or another parent)
        moved = m.move_item(test_item_id, jeep_loc["id"] if jeep_loc else loc_id)
        print("Moved successfully:", moved.get("parent", {}).get("name") or "Parent updated")

        print("\n=== 9. Testing maintenance log ===")
        maint_entry = m.create_maintenance_entry(
            entity_id=test_item_id,
            name="Vymena uhlikov",
            description="Preventivny servis motora",
            cost="25.00",
            completed_date="2026-10-13"
        )
        print("Created maintenance entry:", maint_entry.get("name"), "Cost:", maint_entry.get("cost"))
        log = m.get_maintenance_log(test_item_id)
        print(f"Maintenance log count: {len(log)}")
        assert len(log) > 0

        print("\n=== 10. Testing add_external_link() ===")
        link_res = m.add_external_link(
            entity_id=test_item_id,
            title="Manual skrutkovaca",
            url="https://example.com/bosch-manual.pdf"
        )
        attachments = link_res.get("attachments", [])
        print("Attachments count:", len(attachments))
        assert any(a.get("title") == "Manual skrutkovaca" for a in attachments)

        print("\n=== 11. Testing duplicate_item() ===")
        dup = m.duplicate_item(test_item_id, copy_prefix="Kopia - ")
        dup_id = dup["id"]
        print(f"Created duplicate: {dup['name']} (ID: {dup_id})")
        # Clean up duplicate immediately
        m.delete_item(dup_id)
        print("Duplicate deleted.")

        print("\n=== 12. Testing create_tag() and delete_tag() ===")
        tag = m.create_tag(name="TestTagAuto", description="Testovaci tag", color="#10b981")
        tag_id = tag["id"]
        print(f"Created tag: {tag['name']} (ID: {tag_id})")
        m.delete_tag(tag_id)
        print("Tag deleted.")

    finally:
        print("\n=== 13. Cleaning up test item and location ===")
        try:
            m.delete_item(test_item_id)
            print("Deleted test item.")
        except Exception as e:
            print("Error deleting test item:", e)
        try:
            m.delete_item(loc_id)
            print("Deleted test location.")
        except Exception as e:
            print("Error deleting test location:", e)

    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_tests()
