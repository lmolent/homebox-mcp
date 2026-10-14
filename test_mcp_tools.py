# /// script
# dependencies = ["fastmcp", "httpx", "python-dotenv"]
# ///
"""Automated end-to-end verification of all Homebox MCP tools."""
import os
import sys

from dotenv import load_dotenv

# Load environment variables from .env if present
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    load_dotenv(env_file)

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
    first_loc = locs[0] if locs else None
    if first_loc:
        print(f"Sample location: {first_loc['name']} (ID: {first_loc['id']}, Path: {first_loc['full_path']})")

    print("\n=== 3. Testing search_items() ===")
    items_search = m.search_items(page_size=5)
    print(f"Total items found in search: {items_search.get('total', 0)}")

    loc_id = None
    test_item_id = None
    dup_id = None
    tag_id = None

    print("\n=== 4. Testing create_location() ===")
    new_loc = m.create_location(name="Test MCP Workshop", description="Temporary test location")
    loc_id = new_loc["id"]
    print(f"Created location: {new_loc['name']} (ID: {loc_id})")

    try:
        print("\n=== 5. Testing create_item() with metadata ===")
        new_item = m.create_item(
            name="Test Cordless Screwdriver",
            description="Cordless drill/driver 18V",
            parent_id=loc_id,
            quantity=1,
            serial_number="SN-TEST-9988",
            model_number="MOD-18V-PRO",
            manufacturer="Bosch",
            notes="MCP verification test notes",
            purchase_price=129.99,
        )
        test_item_id = new_item["id"]
        print(f"Created item: {new_item['name']} (ID: {test_item_id})")
        assert new_item.get("serialNumber") == "SN-TEST-9988"
        assert new_item.get("manufacturer") == "Bosch"

        print("\n=== 6. Testing get_item_path() and get_item() ===")
        path = m.get_item_path(test_item_id)
        print("Path breadcrumbs:", " > ".join(p.get("name", "") for p in path))
        assert len(path) >= 1

        fetched_item = m.get_item(test_item_id)
        assert fetched_item.get("name") == "Test Cordless Screwdriver"

        # Test asset lookup dynamically if Homebox assigned an asset ID
        asset_id = fetched_item.get("assetId")
        if asset_id:
            print(f"Testing get_item_by_asset_id with dynamic asset ID: {asset_id}")
            asset_res = m.get_item_by_asset_id(str(asset_id))
            assert "items" in asset_res or "name" in asset_res

        print("\n=== 7. Testing update_item() (safe PUT merge) ===")
        updated = m.update_item(
            test_item_id,
            {
                "description": "Updated screwdriver description",
                "quantity": 2,
                "notes": "Notes updated successfully",
            },
        )
        print(f"Updated description: {updated.get('description')}, quantity: {updated.get('quantity')}")
        assert updated.get("description") == "Updated screwdriver description"
        assert updated.get("quantity") == 2
        assert updated.get("serialNumber") == "SN-TEST-9988"  # Preserved!

        print("\n=== 8. Testing move_item() ===")
        moved = m.move_item(test_item_id, loc_id)
        print("Moved successfully:", moved.get("parent", {}).get("name") or "Parent updated")

        print("\n=== 9. Testing maintenance log ===")
        maint_entry = m.create_maintenance_entry(
            entity_id=test_item_id,
            name="Motor brush replacement",
            description="Preventive motor maintenance",
            cost="25.00",
            completed_date="2026-10-13",
        )
        print("Created maintenance entry:", maint_entry.get("name"), "Cost:", maint_entry.get("cost"))
        log = m.get_maintenance_log(test_item_id)
        print(f"Maintenance log count: {len(log)}")
        assert len(log) > 0

        print("\n=== 10. Testing add_external_link() ===")
        link_res = m.add_external_link(
            entity_id=test_item_id,
            title="Screwdriver user manual",
            url="https://example.com/bosch-manual.pdf",
        )
        attachments = link_res.get("attachments", [])
        print("Attachments count:", len(attachments))
        assert any(a.get("title") == "Screwdriver user manual" for a in attachments)

        print("\n=== 11. Testing duplicate_item() ===")
        dup = m.duplicate_item(test_item_id, copy_prefix="Copy of ")
        dup_id = dup["id"]
        print(f"Created duplicate: {dup['name']} (ID: {dup_id})")
        m.delete_item(dup_id)
        dup_id = None
        print("Duplicate deleted.")

        print("\n=== 12. Testing create_tag() and delete_tag() ===")
        tag = m.create_tag(name="TestTagAutomotive", description="Test tag", color="#10b981")
        tag_id = tag["id"]
        print(f"Created tag: {tag['name']} (ID: {tag_id})")
        m.delete_tag(tag_id)
        tag_id = None
        print("Tag deleted.")

    finally:
        print("\n=== 13. Cleaning up test item and location ===")
        if dup_id:
            try:
                m.delete_item(dup_id)
            except Exception as e:
                print("Error deleting duplicate:", e)
        if tag_id:
            try:
                m.delete_tag(tag_id)
            except Exception as e:
                print("Error deleting tag:", e)
        if test_item_id:
            try:
                m.delete_item(test_item_id)
                print("Deleted test item.")
            except Exception as e:
                print("Error deleting test item:", e)
        if loc_id:
            try:
                m.delete_item(loc_id)
                print("Deleted test location.")
            except Exception as e:
                print("Error deleting test location:", e)

    print("\n>>> ALL TESTS PASSED SUCCESSFULLY! <<<")


if __name__ == "__main__":
    run_tests()
