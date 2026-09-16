"""Admin-focused regression checks for status persistence, export, CMS schema validation, and auth guards."""

import uuid
import pytest


def _origin_headers(base_url: str):
    return {"Origin": base_url}


@pytest.fixture()
def admin_session(api_client, base_url, admin_credentials):
    # Auth module: establish admin cookie session for protected admin routes
    login = api_client.post(
        f"{base_url}/api/auth/login",
        json=admin_credentials,
        headers=_origin_headers(base_url),
    )
    assert login.status_code == 200
    return api_client


class TestAdminWorkflowRegression:
    # Admin routes: unauthorized denial and core dashboard data endpoints
    def test_admin_endpoints_reject_unauthenticated(self, api_client, base_url):
        for endpoint in ["overview", "leads", "orders", "analytics", "export"]:
            r = api_client.get(f"{base_url}/api/admin/{endpoint}")
            assert r.status_code == 401
            assert "sign-in" in r.json().get("detail", "").lower()

    def test_export_returns_valid_payload(self, admin_session, base_url):
        r = admin_session.get(f"{base_url}/api/admin/export")
        assert r.status_code == 200
        data = r.json()
        assert data["schema_version"] == "1.0"
        assert isinstance(data.get("products"), list)
        assert isinstance(data.get("orders"), list)
        assert isinstance(data.get("leads"), list)
        assert isinstance(data.get("content"), dict)
        assert data["content"].get("id") == "site"

    def test_analytics_records_shape(self, admin_session, base_url):
        r = admin_session.get(f"{base_url}/api/admin/analytics")
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            sample = rows[0]
            assert isinstance(sample.get("name"), str)
            assert sample.get("audience") in ["consumer", "reseller"]
            assert isinstance(sample.get("count"), int)

    # Leads/orders module: patch status and verify persisted through re-fetch
    def test_lead_status_update_persists(self, api_client, admin_session, base_url):
        lead_payload = {
            "type": "reseller",
            "name": f"QA TEST Lead {uuid.uuid4().hex[:6]}",
            "mobile": "+919876541234",
            "email": f"qa.lead.{uuid.uuid4().hex[:6]}@example.com",
            "city": "Pune",
            "community_type": "Friends & family",
            "network_size": "25–50 people",
            "starter_option": "starter-4",
            "whatsapp": "+919876541234",
            "message": "QA TEST lead for status patch",
            "consent": True,
            "attribution": {"utm_source": "pytest-iter2"},
        }
        created = api_client.post(f"{base_url}/api/leads", json=lead_payload)
        assert created.status_code == 200
        lead_id = created.json()["id"]

        update = admin_session.patch(f"{base_url}/api/admin/leads/{lead_id}", json={"status": "CONTACTED"})
        assert update.status_code == 200
        assert update.json()["status"] == "CONTACTED"

        check = admin_session.get(f"{base_url}/api/admin/leads")
        assert check.status_code == 200
        matched = [x for x in check.json() if x["id"] == lead_id]
        assert len(matched) == 1
        assert matched[0]["status"] == "CONTACTED"

    def test_order_status_update_persists(self, api_client, admin_session, base_url):
        products = api_client.get(f"{base_url}/api/products").json()
        available = [p for p in products if p.get("available")]
        assert available
        product_id = available[0]["id"]

        order_payload = {
            "name": "QA TEST Order",
            "email": f"qa.order.{uuid.uuid4().hex[:6]}@example.com",
            "mobile": "+919876549999",
            "address": "QA TEST address",
            "city": "Sangli",
            "pincode": "416416",
            "consent": True,
            "request_id": f"iter2-{uuid.uuid4()}",
            "attribution": {"utm_source": "pytest-iter2"},
            "items": [{"product_id": product_id, "quantity": 1}],
        }
        created = api_client.post(f"{base_url}/api/orders", json=order_payload)
        assert created.status_code == 200
        order_id = created.json()["id"]

        update = admin_session.patch(f"{base_url}/api/admin/orders/{order_id}", json={"status": "CONFIRMED"})
        assert update.status_code == 200
        assert update.json()["status"] == "CONFIRMED"

        check = admin_session.get(f"{base_url}/api/admin/orders")
        assert check.status_code == 200
        matched = [x for x in check.json() if x["id"] == order_id]
        assert len(matched) == 1
        assert matched[0]["status"] == "CONFIRMED"

    # Content/CMS module: reject invalid nested JSON and ensure valid save succeeds
    def test_content_invalid_nested_kits_type_rejected_without_corruption(self, admin_session, base_url):
        current = admin_session.get(f"{base_url}/api/content")
        assert current.status_code == 200
        before = current.json()

        bad_payload = {"reseller": {"kits": {"wrong": "type"}}}
        bad = admin_session.put(f"{base_url}/api/admin/content", json=bad_payload)
        assert bad.status_code in [400, 422]

        after = admin_session.get(f"{base_url}/api/content")
        assert after.status_code == 200
        assert after.json()["reseller"]["kits"] == before["reseller"]["kits"]

    def test_content_valid_save_and_restore_succeeds(self, admin_session, base_url):
        current = admin_session.get(f"{base_url}/api/content")
        assert current.status_code == 200
        original = current.json()

        new_value = f"QA TEST announcement {uuid.uuid4().hex[:6]}"
        saved = admin_session.put(
            f"{base_url}/api/admin/content",
            json={"announcement": new_value},
        )
        assert saved.status_code == 200
        assert saved.json()["announcement"] == new_value

        verify = admin_session.get(f"{base_url}/api/content")
        assert verify.status_code == 200
        assert verify.json()["announcement"] == new_value

        restore = admin_session.put(
            f"{base_url}/api/admin/content",
            json={"announcement": original["announcement"]},
        )
        assert restore.status_code == 200
        assert restore.json()["announcement"] == original["announcement"]
