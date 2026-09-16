"""Critical auth + commerce + admin guard regression coverage for SANGLEY."""

import os
import uuid
from pathlib import Path

import pytest
from pymongo import MongoClient


def _frontend_origin(base_url: str) -> str:
    return base_url


def _admin_headers(origin: str):
    return {"Origin": origin}


class TestPublicCommerce:
    """Public APIs: health, catalog, quote, order, leads."""

    def test_health(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/")
        assert r.status_code == 200
        data = r.json()
        assert data["brand"] == "SANGLEY"
        assert data["status"] == "ready"

    def test_products_and_product_details(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/products")
        assert r.status_code == 200
        products = r.json()
        assert isinstance(products, list)
        assert len(products) >= 4
        handle = products[0]["handle"]

        detail = api_client.get(f"{base_url}/api/products/{handle}")
        assert detail.status_code == 200
        item = detail.json()
        assert item["handle"] == handle
        assert isinstance(item["price"], (int, float))

    def test_quote_valid_bundle_and_price(self, api_client, base_url):
        products = api_client.get(f"{base_url}/api/products").json()
        available = [p for p in products if p.get("available")]
        assert len(available) >= 1
        pid = available[0]["id"]

        payload = {
            "items": [
                {
                    "bundle_size": 4,
                    "quantity": 1,
                    "selections": {pid: 4},
                }
            ]
        }
        r = api_client.post(f"{base_url}/api/cart/quote", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["subtotal"] == pytest.approx(596, rel=0.001)
        assert data["checkout_mode"] == "enquiry"

    def test_quote_invalid_bundle_count_rejected(self, api_client, base_url):
        products = api_client.get(f"{base_url}/api/products").json()
        pid = products[0]["id"]
        payload = {
            "items": [
                {
                    "bundle_size": 4,
                    "quantity": 1,
                    "selections": {pid: 3},
                }
            ]
        }
        r = api_client.post(f"{base_url}/api/cart/quote", json=payload)
        assert r.status_code == 400
        assert "exactly 4 packs" in r.json().get("detail", "")

    def test_order_idempotency_by_request_id(self, api_client, base_url):
        products = api_client.get(f"{base_url}/api/products").json()
        pid = [p for p in products if p.get("available")][0]["id"]
        request_id = f"pytest-{uuid.uuid4()}"
        body = {
            "name": "QA TEST User",
            "email": "qatest@example.com",
            "mobile": "+919876543210",
            "address": "QA TEST Address, Sangli",
            "city": "Sangli",
            "pincode": "416416",
            "consent": True,
            "request_id": request_id,
            "attribution": {"utm_source": "pytest"},
            "items": [{"product_id": pid, "quantity": 2}],
        }
        first = api_client.post(f"{base_url}/api/orders", json=body)
        assert first.status_code == 200
        first_data = first.json()
        second = api_client.post(f"{base_url}/api/orders", json=body)
        assert second.status_code == 200
        second_data = second.json()
        assert second_data["id"] == first_data["id"]
        assert second_data["subtotal"] == first_data["subtotal"]

    def test_lead_submission_persists(self, api_client, base_url):
        body = {
            "type": "reseller",
            "name": "QA TEST Lead",
            "mobile": "+919123456789",
            "email": "qa.lead@example.com",
            "city": "Pune",
            "community_type": "Friends & family",
            "network_size": "25–50 people",
            "starter_option": "starter-4",
            "whatsapp": "+919123456789",
            "message": "QA TEST lead submission",
            "consent": True,
            "attribution": {"utm_campaign": "qa"},
        }
        r = api_client.post(f"{base_url}/api/leads", json=body)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["id"], str)
        assert "team will get in touch" in data["message"]


class TestAuthAndAdminGuards:
    """Auth session/cookies/lockout and admin endpoint guards."""

    def test_admin_requires_auth(self, api_client, base_url):
        r = api_client.get(f"{base_url}/api/admin/overview")
        assert r.status_code == 401
        assert "sign-in" in r.json().get("detail", "").lower()

    def test_auth_login_sets_httponly_cookies_and_me_works(self, api_client, base_url, admin_credentials):
        origin = _frontend_origin(base_url)
        login = api_client.post(
            f"{base_url}/api/auth/login",
            json=admin_credentials,
            headers=_admin_headers(origin),
        )
        assert login.status_code == 200
        set_cookie = login.headers.get("set-cookie", "")
        assert "access_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Secure" in set_cookie

        me = api_client.get(f"{base_url}/api/auth/me")
        assert me.status_code == 200
        user = me.json()
        assert user["email"] == admin_credentials["email"].lower()
        assert user["role"] == "admin"

    def test_refresh_and_logout(self, api_client, base_url, admin_credentials):
        origin = _frontend_origin(base_url)
        login = api_client.post(
            f"{base_url}/api/auth/login",
            json=admin_credentials,
            headers=_admin_headers(origin),
        )
        assert login.status_code == 200

        refresh = api_client.post(f"{base_url}/api/auth/refresh", headers=_admin_headers(origin))
        assert refresh.status_code == 200
        assert refresh.json()["role"] == "admin"

        logout = api_client.post(f"{base_url}/api/auth/logout", headers=_admin_headers(origin))
        assert logout.status_code == 200
        me = api_client.get(f"{base_url}/api/auth/me")
        assert me.status_code == 401

    def test_invalid_origin_rejected_for_authenticated_mutation(self, api_client, base_url, admin_credentials):
        login = api_client.post(
            f"{base_url}/api/auth/login",
            json=admin_credentials,
            headers=_admin_headers(base_url),
        )
        assert login.status_code == 200
        r = api_client.post(
            f"{base_url}/api/auth/logout",
            headers={"Origin": "https://evil.example.com"},
        )
        assert r.status_code == 403
        assert "origin" in r.json().get("detail", "").lower()

    def test_bruteforce_lockout_after_five_fails(self, api_client, base_url):
        origin = _frontend_origin(base_url)
        email = f"qa-lock-{uuid.uuid4().hex[:8]}@example.com"
        payload = {"email": email, "password": "wrong-password"}
        statuses = []
        for _ in range(6):
            r = api_client.post(f"{base_url}/api/auth/login", json=payload, headers=_admin_headers(origin))
            statuses.append(r.status_code)
        assert statuses[-1] == 429


class TestAuthStorageAndSeed:
    """Mongo checks for bcrypt format and unique email index."""

    def test_admin_hash_format_and_users_email_unique_index(self):
        env_path = Path("/app/backend/.env")
        mongo_url = None
        db_name = None
        for line in env_path.read_text().splitlines():
            if line.startswith("MONGO_URL="):
                mongo_url = line.split("=", 1)[1].strip().strip('"')
            if line.startswith("DB_NAME="):
                db_name = line.split("=", 1)[1].strip().strip('"')
        if not mongo_url or not db_name:
            pytest.skip("Mongo env not available")

        client = MongoClient(mongo_url)
        db = client[db_name]
        admin_email = os.environ.get("ADMIN_EMAIL")
        if not admin_email:
            creds = Path("/app/memory/test_credentials.md").read_text()
            for line in creds.splitlines():
                if line.strip().startswith("- Email:"):
                    admin_email = line.split(":", 1)[1].strip()
                    break
        if not admin_email:
            pytest.skip("Admin email unavailable for bcrypt validation")
        admin_email = admin_email.lower()
        user = db.users.find_one({"email": admin_email})
        assert user is not None
        assert isinstance(user.get("password_hash"), str)
        assert user["password_hash"].startswith("$2b$")

        indexes = db.users.index_information()
        unique_email_index = [v for v in indexes.values() if v.get("unique") and ("email", 1) in v.get("key", [])]
        assert len(unique_email_index) >= 1
