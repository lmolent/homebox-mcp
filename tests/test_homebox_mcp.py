"""Unit tests for homebox_mcp tools with mocked API responses."""
from unittest.mock import MagicMock, patch
import pytest

import homebox_mcp as m

VALID_UUID = "12345678-1234-5678-1234-567812345678"
VALID_PARENT_UUID = "87654321-4321-8765-4321-876543218765"


class TestUUIDValidation:
    def test_valid_uuid(self):
        assert m._validate_uuid(VALID_UUID) == VALID_UUID

    def test_invalid_uuid(self):
        with pytest.raises(ValueError, match="must be a valid UUID"):
            m._validate_uuid("invalid-uuid-string", "test_id")

    def test_empty_uuid(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            m._validate_uuid("", "test_id")


class TestBarcodeSearch:
    @patch("homebox_mcp.call")
    def test_search_by_barcode_sends_product_ean_and_data(self, mock_call):
        mock_call.return_value = [{"title": "Test Product"}]
        res = m.search_by_barcode("5035048748428")
        mock_call.assert_called_once_with(
            "GET",
            "/products/search-from-barcode",
            params={"productEAN": "5035048748428", "data": "5035048748428"},
        )
        assert len(res) == 1


class TestExternalLink:
    @patch("homebox_mcp.call")
    def test_valid_urls(self, mock_call):
        mock_call.return_value = {"ok": True}
        m.add_external_link(VALID_UUID, "Manual", "https://example.com/manual.pdf")
        mock_call.assert_called_once_with(
            "POST",
            f"/entities/{VALID_UUID}/attachments/external",
            json={
                "title": "Manual",
                "external_id": "https://example.com/manual.pdf",
                "attachment_type": "document",
                "source_type": "link",
            },
        )

    def test_invalid_url_schemes(self):
        with pytest.raises(ValueError, match="must start with http:// or https://"):
            m.add_external_link(VALID_UUID, "Exploit", "javascript:alert(1)")

        with pytest.raises(ValueError, match="must start with http:// or https://"):
            m.add_external_link(VALID_UUID, "Data", "data:text/html;base64,...")

        with pytest.raises(ValueError, match="must start with http:// or https://"):
            m.add_external_link(VALID_UUID, "FTP", "ftp://example.com/file")


class TestListLocations:
    @patch("homebox_mcp.call")
    def test_empty_or_null_tree(self, mock_call):
        mock_call.return_value = None
        assert m.list_locations() == []

    @patch("homebox_mcp.call")
    def test_nested_tree_flattening(self, mock_call):
        mock_call.return_value = [
            {
                "id": "loc-1",
                "name": "Garage",
                "type": "location",
                "children": [
                    {
                        "id": "loc-2",
                        "name": "Toolbox",
                        "type": "location",
                        "children": [],
                    }
                ],
            }
        ]
        locs = m.list_locations()
        assert len(locs) == 2
        assert locs[0]["full_path"] == "Garage"
        assert locs[1]["full_path"] == "Garage > Toolbox"


class TestCreateTag:
    @patch("homebox_mcp.call")
    def test_create_tag_without_parent(self, mock_call):
        mock_call.return_value = {"id": "tag-1", "name": "Tools"}
        m.create_tag(name="Tools", color="#ff0000")
        mock_call.assert_called_once_with(
            "POST",
            "/tags",
            json={"name": "Tools", "description": "", "color": "#ff0000"},
        )

    @patch("homebox_mcp.call")
    def test_create_tag_with_parent(self, mock_call):
        mock_call.return_value = {"id": "tag-2", "name": "Hand Tools"}
        m.create_tag(name="Hand Tools", parent_id=VALID_PARENT_UUID)
        mock_call.assert_called_once_with(
            "POST",
            "/tags",
            json={
                "name": "Hand Tools",
                "description": "",
                "color": "",
                "parentId": VALID_PARENT_UUID,
            },
        )


class TestCreateAndModifyItems:
    @patch("homebox_mcp._get_entity_type_id", return_value="type-item")
    @patch("homebox_mcp.call")
    def test_create_item_basic_no_update_step(self, mock_call, mock_type):
        # When no serialNumber, notes, or purchasePrice, single POST is made
        mock_call.return_value = {"id": VALID_UUID, "name": "Wrench"}
        res = m.create_item(
            name="Wrench",
            model_number="WR-10",
            manufacturer="Stanley",
        )
        assert mock_call.call_count == 1
        mock_call.assert_called_once_with(
            "POST",
            "/entities",
            json={
                "name": "Wrench",
                "description": "",
                "quantity": 1,
                "tagIds": [],
                "entityTypeId": "type-item",
                "modelNumber": "WR-10",
                "manufacturer": "Stanley",
            },
        )
        assert res["id"] == VALID_UUID

    @patch("homebox_mcp.update_item")
    @patch("homebox_mcp._get_entity_type_id", return_value="type-item")
    @patch("homebox_mcp.call")
    def test_create_item_with_extended_fields_calls_update(self, mock_call, mock_type, mock_update):
        mock_call.return_value = {"id": VALID_UUID, "name": "Drill"}
        mock_update.return_value = {"id": VALID_UUID, "name": "Drill", "serialNumber": "SN-123"}

        res = m.create_item(
            name="Drill",
            serial_number="SN-123",
            purchase_price=89.99,
        )
        mock_update.assert_called_once_with(
            id=VALID_UUID,
            fields={"serialNumber": "SN-123", "purchasePrice": 89.99},
        )
        assert res["serialNumber"] == "SN-123"
