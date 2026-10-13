# /// script
# dependencies = ["fastmcp", "httpx"]
# ///
"""Production-grade MCP server for Homebox inventory management.
Run: uv run homebox_mcp.py
"""
import os
import sys
from typing import Any

import httpx
from fastmcp import FastMCP

# Optional: Load .env file from script directory if present
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

BASE_URL = os.getenv("HOMEBOX_URL", "http://localhost:7745").rstrip("/") + "/api/v1"
API_KEY = os.getenv("HOMEBOX_API_KEY")
if not API_KEY:
    # Helpful reminder in stderr for CLI execution
    sys.stderr.write("WARNING: HOMEBOX_API_KEY environment variable is not set.\n")

mcp = FastMCP("homebox")
http = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {API_KEY}"} if API_KEY else {},
    timeout=30.0,
)

# In-memory cache for entity type IDs (item vs location)
_TYPE_CACHE: dict[str, str] = {}


def call(method: str, path: str, **kw) -> Any:
    """Execute an HTTP request against Homebox API with sanitized error handling."""
    try:
        r = http.request(method, path, **kw)
        r.raise_for_status()
        return r.json() if r.content else {"ok": True}
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 404:
            raise RuntimeError(f"Entity or resource not found at '{path}' (404).")
        msg = e.response.text if len(e.response.text) < 200 else f"HTTP {status}"
        raise RuntimeError(f"Homebox API error ({status}): {msg}")
    except httpx.RequestError:
        raise RuntimeError("Failed to communicate with Homebox API server.")


def _get_entity_type_id(is_location: bool) -> str | None:
    """Resolve and cache the UUID for item or location entity type."""
    cache_key = "location" if is_location else "item"
    if cache_key in _TYPE_CACHE:
        return _TYPE_CACHE[cache_key]
    try:
        types = call("GET", "/entity-types")
        for t in types:
            if t.get("isLocation") is True:
                _TYPE_CACHE["location"] = t["id"]
            elif t.get("isLocation") is False:
                _TYPE_CACHE["item"] = t["id"]
        return _TYPE_CACHE.get(cache_key)
    except Exception:
        return None


# ==============================================================================
# Search & Query Tools
# ==============================================================================


@mcp.tool
def search_items(
    query: str = "",
    parent_ids: list[str] | None = None,
    tag_ids: list[str] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Search inventory items and locations by text query with optional filters.

    Args:
        query: Search text to match in name, description, model, serial number, etc.
        parent_ids: Optional list of parent location UUIDs to restrict results to specific locations.
        tag_ids: Optional list of tag UUIDs to filter results by tags.
        page: Page number (1-based, default: 1).
        page_size: Number of results per page (default: 50).
    """
    params: list[tuple[str, Any]] = [("q", query), ("page", page), ("pageSize", page_size)]
    if parent_ids:
        for pid in parent_ids:
            params.append(("parentIds", pid))
    if tag_ids:
        for tid in tag_ids:
            params.append(("tags", tid))
    return call("GET", "/entities", params=params)


@mcp.tool
def get_item(id: str) -> dict:
    """Get full details of an inventory item or location by its UUID.

    Returns complete entity data including attachments, warranty, purchase details,
    serial number, custom fields, and parent information.
    """
    return call("GET", f"/entities/{id}")


@mcp.tool
def get_item_by_asset_id(asset_id: str) -> dict:
    """Find an item or location by its short Homebox asset ID tag (e.g. '000-015').

    Use this when the user mentions an asset label or tag code printed on a physical sticker.
    """
    return call("GET", f"/assets/{asset_id}")


@mcp.tool
def get_item_path(id: str) -> list[dict]:
    """Get the full location hierarchy / breadcrumb path from the root location down to the entity.

    Essential for answering 'Where is item X located?' - returns the chain of containers/rooms
    (e.g., Garage > Shelf 2 > Toolbox > Screwdriver).
    """
    return call("GET", f"/entities/{id}/path")


@mcp.tool
def search_by_barcode(barcode: str) -> list[dict]:
    """Search product info by barcode or EAN number using Homebox product lookup."""
    return call("GET", "/products/search-from-barcode", params={"data": barcode})


# ==============================================================================
# Item Management Tools
# ==============================================================================


@mcp.tool
def create_item(
    name: str,
    description: str = "",
    parent_id: str | None = None,
    quantity: int = 1,
    tag_ids: list[str] | None = None,
    entity_type_id: str | None = None,
    serial_number: str = "",
    model_number: str = "",
    manufacturer: str = "",
    notes: str = "",
    purchase_price: float | None = None,
) -> dict:
    """Create a new inventory item in a given location or container.

    Args:
        name: Name of the item (required).
        description: Description of the item.
        parent_id: UUID of the location or container where this item is stored. Use list_locations to find IDs.
        quantity: Item quantity (default: 1).
        tag_ids: Optional list of tag UUIDs.
        entity_type_id: Optional custom entity type ID. Defaults to standard item type.
        serial_number: Hardware serial number.
        model_number: Product model number.
        manufacturer: Brand or manufacturer name.
        notes: Additional private notes or instructions.
        purchase_price: Purchase price as a float.
    """
    target_type = entity_type_id or _get_entity_type_id(is_location=False)
    body = {
        "name": name,
        "description": description,
        "quantity": quantity,
        "parentId": parent_id,
        "tagIds": tag_ids or [],
        "entityTypeId": target_type,
    }
    res = call("POST", "/entities", json={k: v for k, v in body.items() if v is not None})

    # Apply extended metadata via full update if provided
    extended_fields: dict[str, Any] = {}
    if serial_number:
        extended_fields["serialNumber"] = serial_number
    if model_number:
        extended_fields["modelNumber"] = model_number
    if manufacturer:
        extended_fields["manufacturer"] = manufacturer
    if notes:
        extended_fields["notes"] = notes
    if purchase_price is not None:
        extended_fields["purchasePrice"] = purchase_price

    if extended_fields and res.get("id"):
        return update_item(id=res["id"], fields=extended_fields)

    return res


@mcp.tool
def update_item(id: str, fields: dict) -> dict:
    """Update fields on an existing item or location.

    Performs a safe merge and full update (PUT), allowing modification of all fields:
    name, description, notes, quantity, parent_id/parentId, tag_ids/tagIds,
    serial_number/serialNumber, model_number/modelNumber, manufacturer,
    purchase_price/purchasePrice, purchase_date/purchaseDate, warranty_expires/warrantyExpires,
    insured, archived.
    """
    curr = call("GET", f"/entities/{id}")

    aliases = {
        "parent_id": "parentId",
        "tag_ids": "tagIds",
        "entity_type_id": "entityTypeId",
        "serial_number": "serialNumber",
        "model_number": "modelNumber",
        "purchase_price": "purchasePrice",
        "purchase_date": "purchaseDate",
        "purchase_from": "purchaseFrom",
        "warranty_expires": "warrantyExpires",
        "warranty_details": "warrantyDetails",
        "lifetime_warranty": "lifetimeWarranty",
    }
    normalized: dict[str, Any] = {}
    for k, v in fields.items():
        normalized[aliases.get(k, k)] = v

    payload = {
        "id": id,
        "name": curr.get("name", ""),
        "description": curr.get("description", ""),
        "notes": curr.get("notes", ""),
        "quantity": curr.get("quantity", 1),
        "parentId": curr.get("parent", {}).get("id") if curr.get("parent") else None,
        "entityTypeId": curr.get("entityType", {}).get("id") if curr.get("entityType") else None,
        "tagIds": [t["id"] for t in curr.get("tags", [])] if "tags" in curr else [],
        "serialNumber": curr.get("serialNumber", ""),
        "modelNumber": curr.get("modelNumber", ""),
        "manufacturer": curr.get("manufacturer", ""),
        "purchasePrice": curr.get("purchasePrice", 0),
        "purchaseDate": curr.get("purchaseDate", ""),
        "purchaseFrom": curr.get("purchaseFrom", ""),
        "warrantyExpires": curr.get("warrantyExpires", ""),
        "warrantyDetails": curr.get("warrantyDetails", ""),
        "lifetimeWarranty": curr.get("lifetimeWarranty", False),
        "insured": curr.get("insured", False),
        "archived": curr.get("archived", False),
    }
    payload.update(normalized)
    return call("PUT", f"/entities/{id}", json=payload)


@mcp.tool
def delete_item(id: str) -> dict:
    """Delete an item or location by UUID."""
    return call("DELETE", f"/entities/{id}")


@mcp.tool
def duplicate_item(id: str, copy_prefix: str = "Copy of ") -> dict:
    """Duplicate an existing item or location with all its attributes."""
    return call("POST", f"/entities/{id}/duplicate", json={"copyPrefix": copy_prefix})


# ==============================================================================
# Location & Hierarchy Tools
# ==============================================================================


@mcp.tool
def create_location(name: str, description: str = "", parent_id: str | None = None) -> dict:
    """Create a new physical location, room, building, vehicle, or sub-container.

    Args:
        name: Name of the location (e.g. 'Garage 1', 'Workshop', 'Shelf A', 'Van').
        description: Description of the location.
        parent_id: Optional parent location UUID. If omitted, creates a root-level location.
                   If provided, creates a nested sub-location inside that parent.
    """
    loc_type_id = _get_entity_type_id(is_location=True)
    body = {
        "name": name,
        "description": description,
        "parentId": parent_id,
        "entityTypeId": loc_type_id,
        "quantity": 1,
    }
    return call("POST", "/entities", json={k: v for k, v in body.items() if v is not None})


@mcp.tool
def list_locations() -> list[dict]:
    """Get a flat list of all locations with their ID, name, and full hierarchy path.

    Call this first to discover valid destination IDs when user wants to place or move items.
    """
    tree = call("GET", "/entities/tree", params={"withItems": False})
    locations: list[dict] = []

    def walk(nodes: list[dict], parent_path: str = ""):
        for node in nodes:
            name = node.get("name", "")
            full_path = f"{parent_path} > {name}" if parent_path else name
            locations.append({
                "id": node.get("id"),
                "name": name,
                "full_path": full_path,
                "type": node.get("type", "location"),
            })
            if node.get("children"):
                walk(node["children"], full_path)

    walk(tree)
    return locations


@mcp.tool
def location_tree(with_items: bool = False) -> list:
    """Get the full hierarchical tree structure of locations (optionally including items)."""
    return call("GET", "/entities/tree", params={"withItems": with_items})


@mcp.tool
def move_item(id: str, new_parent_id: str) -> dict:
    """Move an item or sub-location into a new location or container.

    Args:
        id: UUID of the item or container to move.
        new_parent_id: UUID of the destination location (use list_locations to find IDs).
    """
    return update_item(id=id, fields={"parentId": new_parent_id})


# ==============================================================================
# Maintenance & Service Log Tools
# ==============================================================================


@mcp.tool
def get_maintenance_log(entity_id: str) -> list[dict]:
    """Get the maintenance and service history log for an item (vehicle, machine, tool, etc.)."""
    return call("GET", f"/entities/{entity_id}/maintenance")


@mcp.tool
def create_maintenance_entry(
    entity_id: str,
    name: str,
    description: str = "",
    cost: str = "",
    completed_date: str = "",
    scheduled_date: str = "",
) -> dict:
    """Record a completed or scheduled maintenance / service entry for an item.

    Use this for tracking vehicle maintenance (Jeep, Caravan), bike service, tool repairs,
    inspections, battery replacements, or oil changes.

    Args:
        entity_id: UUID of the item undergoing maintenance.
        name: Name of the service entry (e.g. 'Oil change', 'STK', 'Chain replacement').
        description: Detailed notes of the service done.
        cost: Cost as a string or number (e.g. '85.50').
        completed_date: Date completed in YYYY-MM-DD format (if completed).
        scheduled_date: Date scheduled in YYYY-MM-DD format (if planned).
    """
    payload = {
        "name": name,
        "description": description,
        "cost": str(cost) if cost else "",
        "completedDate": completed_date,
        "scheduledDate": scheduled_date,
    }
    return call("POST", f"/entities/{entity_id}/maintenance", json={k: v for k, v in payload.items() if v != ""})


# ==============================================================================
# Tags & Metadata Tools
# ==============================================================================


@mcp.tool
def list_tags() -> list[dict]:
    """List all available tags."""
    return call("GET", "/tags")


@mcp.tool
def create_tag(
    name: str,
    description: str = "",
    color: str = "",
    parent_id: str | None = None,
) -> dict:
    """Create a new tag.

    Args:
        name: Tag name (e.g. 'Tools', 'Garden', 'Important').
        description: Optional description.
        color: Optional hex color code (e.g. '#2563eb').
        parent_id: Optional parent tag UUID for tag hierarchies.
    """
    body = {
        "name": name,
        "description": description,
        "color": color,
        "parentId": parent_id or "00000000-0000-0000-0000-000000000000",
    }
    return call("POST", "/tags", json=body)


@mcp.tool
def delete_tag(id: str) -> dict:
    """Delete a tag by UUID."""
    return call("DELETE", f"/tags/{id}")


@mcp.tool
def list_entity_types() -> list[dict]:
    """List all registered entity types (e.g. item vs location)."""
    return call("GET", "/entity-types")


# ==============================================================================
# Attachments & Statistics Tools
# ==============================================================================


@mcp.tool
def add_external_link(entity_id: str, title: str, url: str) -> dict:
    """Attach an external web link (user manual, datasheet, product page, receipt link) to an item or location.

    Args:
        entity_id: UUID of the target item or location.
        title: Title of the link (e.g. 'User Manual PDF', 'Official Store Page').
        url: Full web URL (must start with http:// or https://).
    """
    return call(
        "POST",
        f"/entities/{entity_id}/attachments/external",
        json={
            "title": title,
            "external_id": url,
            "attachment_type": "document",
            "source_type": "link",
        },
    )


@mcp.tool
def get_statistics() -> dict:
    """Get overall inventory statistics (total items, total locations, total tags, total value, warranty counts)."""
    return call("GET", "/groups/statistics")


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport == "sse":
        port = int(os.getenv("PORT", os.getenv("MCP_PORT", "8000")))
        host = os.getenv("HOST", os.getenv("MCP_HOST", "0.0.0.0"))
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")
