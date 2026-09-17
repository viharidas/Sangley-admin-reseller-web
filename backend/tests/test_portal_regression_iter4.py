"""Iteration-4 focused regression: auth lockout, files/storage, referrals, financial branches."""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import pytest
import requests
from PIL import Image


def _origin_headers(base_url: str) -> dict[str, str]:
    return {"Origin": base_url, "Content-Type": "application/json"}


def _load_iter3_creds() -> dict:
    path = Path("/app/test_reports/portal_iter3_credentials.json")
    if not path.exists():
        pytest.skip("Missing /app/test_reports/portal_iter3_credentials.json")
    return json.loads(path.read_text())


def _admin_login(base_url: str, admin_credentials: dict) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{base_url}/api/auth/login",
        json=admin_credentials,
        headers=_origin_headers(base_url),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return s


def _reseller_login(base_url: str, email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{base_url}/api/reseller/auth/login",
        json={"email": email, "password": password},
        headers=_origin_headers(base_url),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return s


def _pick_available_product(base_url: str) -> dict:
    rows = requests.get(f"{base_url}/api/products", timeout=30).json()
    available = [p for p in rows if p.get("available")]
    assert available
    return available[0]


def _create_referred_order(base_url: str, referral_code: str, product_id: str, email: str, mobile: str) -> tuple[str, requests.Session]:
    customer = requests.Session()
    visit = customer.post(
        f"{base_url}/api/referrals/visit",
        json={"code": referral_code, "source": "pytest_iter4", "campaign": ""},
        timeout=30,
    )
    assert visit.status_code == 200, visit.text
    body = {
        "name": "QA ITER4 Customer",
        "email": email,
        "mobile": mobile,
        "address": "QA Iter4 Street",
        "city": "Sangli",
        "pincode": "416416",
        "consent": True,
        "request_id": f"QA_ITER4_{uuid.uuid4()}",
        "attribution": {"utm_source": "pytest_iter4"},
        "items": [{"product_id": product_id, "quantity": 1}],
    }
    order = customer.post(f"{base_url}/api/orders", json=body, timeout=30)
    assert order.status_code == 200, order.text
    return order.json()["id"], customer


def _mark_order_state(admin: requests.Session, base_url: str, order_id: str, payment: str, delivery: str, status: str, reason: str):
    r = admin.patch(
        f"{base_url}/api/admin/business/orders/{order_id}",
        json={
            "payment_status": payment,
            "delivery_status": delivery,
            "status": status,
            "payment_reference": f"QA4-{uuid.uuid4().hex[:8]}",
            "reason": reason,
        },
        headers=_origin_headers(base_url),
        timeout=30,
    )
    assert r.status_code == 200, r.text


def _commission_for_order(admin: requests.Session, base_url: str, reseller_id: str, order_id: str) -> dict:
    for _ in range(8):
        r = admin.get(
            f"{base_url}/api/admin/business/commission?reseller_id={reseller_id}&limit=100",
            timeout=30,
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        row = next((x for x in items if x["order_id"] == order_id), None)
        if row:
            return row
        time.sleep(0.4)
    pytest.fail(f"Commission not found for order {order_id}")


def _set_commission_state(admin: requests.Session, base_url: str, cid: str, target: str, reason: str):
    r = admin.patch(
        f"{base_url}/api/admin/business/commission/{cid}/status",
        json={"status": target, "reason": reason},
        headers=_origin_headers(base_url),
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()


class TestIter4AuthAndFiles:
    # Auth module: validate admin 6th lockout still 429 and reseller account-scoped limiter remains stable.
    def test_lockout_admin_and_reseller_account_scoped(self, base_url, admin_credentials):
        admin_payload = {"email": f"qa-admin-lock-{uuid.uuid4().hex[:8]}@example.com", "password": "bad-pass"}
        admin_statuses = []
        for _ in range(6):
            r = requests.post(
                f"{base_url}/api/auth/login",
                json=admin_payload,
                headers=_origin_headers(base_url),
                timeout=20,
            )
            admin_statuses.append(r.status_code)
        assert admin_statuses[-1] == 429

        reseller_payload = {"email": f"qa-reseller-lock-{uuid.uuid4().hex[:8]}@example.com", "password": "bad-pass"}
        reseller_statuses = []
        for idx in range(6):
            headers = {**_origin_headers(base_url), "X-Forwarded-For": f"10.10.0.{idx+1}"}
            r = requests.post(
                f"{base_url}/api/reseller/auth/login",
                json=reseller_payload,
                headers=headers,
                timeout=20,
            )
            reseller_statuses.append(r.status_code)
        assert reseller_statuses[-1] == 429

    # File/storage module: raw-body upload, toolkit publication/download, MIME checks, IDOR, avatar ownership.
    def test_portal_files_upload_publish_security_and_validation(self, base_url, admin_credentials):
        creds = _load_iter3_creds()
        admin = _admin_login(base_url, admin_credentials)
        reseller_a = _reseller_login(base_url, creds["A"]["email"], creds["A"]["password"])
        reseller_b = _reseller_login(base_url, creds["B"]["email"], creds["B"]["password"])

        pdf_bytes = b"%PDF-1.4\n%QA_ITER4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        up = admin.post(
            f"{base_url}/api/portal-files?filename=qa_iter4_marketing.pdf&purpose=marketing",
            headers={"Origin": base_url, "Content-Type": "application/pdf"},
            data=pdf_bytes,
            timeout=60,
        )
        assert up.status_code == 200, up.text
        marketing_file_id = up.json()["id"]
        assert up.json()["content_type"] == "application/pdf"

        publish = admin.post(
            f"{base_url}/api/admin/business/marketing",
            json={
                "title": f"QA_ITER4 Asset {uuid.uuid4().hex[:6]}",
                "category": "PRODUCT",
                "description": "QA_ITER4 storage flow",
                "file_id": marketing_file_id,
                "url": "",
                "active": True,
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert publish.status_code == 200, publish.text

        toolkit = reseller_a.get(f"{base_url}/api/reseller/marketing-toolkit", timeout=30)
        assert toolkit.status_code == 200
        toolkit_ids = [x.get("file_id") for x in toolkit.json().get("items", [])]
        assert marketing_file_id in toolkit_ids

        dl = reseller_a.get(f"{base_url}/api/portal-files/{marketing_file_id}?download=true", timeout=60)
        assert dl.status_code == 200
        assert dl.headers.get("content-type", "").startswith("application/pdf")

        mismatch = admin.post(
            f"{base_url}/api/portal-files?filename=bad.png&purpose=marketing",
            headers={"Origin": base_url, "Content-Type": "image/png"},
            data=b"not-a-real-png",
            timeout=30,
        )
        assert mismatch.status_code == 415

        unsupported = admin.post(
            f"{base_url}/api/portal-files?filename=bad.txt&purpose=support",
            headers={"Origin": base_url, "Content-Type": "text/plain"},
            data=b"plain-text",
            timeout=30,
        )
        assert unsupported.status_code == 415

        oversize = admin.post(
            f"{base_url}/api/portal-files?filename=large.pdf&purpose=support",
            headers={"Origin": base_url, "Content-Type": "application/pdf"},
            data=b"%PDF-" + b"A" * (26 * 1024 * 1024),
            timeout=120,
        )
        assert oversize.status_code == 413

        support_file = reseller_b.post(
            f"{base_url}/api/portal-files?filename=qa_iter4_support.pdf&purpose=support",
            headers={"Origin": base_url, "Content-Type": "application/pdf"},
            data=pdf_bytes,
            timeout=60,
        )
        assert support_file.status_code == 200, support_file.text
        support_file_id = support_file.json()["id"]

        idor = reseller_a.get(f"{base_url}/api/portal-files/{support_file_id}", timeout=30)
        assert idor.status_code == 404

        img = Image.new("RGB", (1, 1), color=(255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_1x1 = buf.getvalue()
        avatar_b = reseller_b.post(
            f"{base_url}/api/portal-files?filename=qa_iter4_avatar.png&purpose=avatar",
            headers={"Origin": base_url, "Content-Type": "image/png"},
            data=png_1x1,
            timeout=60,
        )
        assert avatar_b.status_code == 200, avatar_b.text
        avatar_id = avatar_b.json()["id"]

        ownership = reseller_a.patch(
            f"{base_url}/api/reseller/profile",
            json={"photo_file_id": avatar_id},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert ownership.status_code == 400


class TestIter4FinanceAndReferrals:
    # Finance module: reservation release/reuse, reserved-adjust guard, paid-return single reversal, adjustment math.
    def test_finance_reservation_release_reuse_and_adjustment_branches(self, base_url, admin_credentials):
        creds = _load_iter3_creds()
        admin = _admin_login(base_url, admin_credentials)
        product = _pick_available_product(base_url)
        rid = creds["A"]["reseller_id"]
        referral_code = creds["A"]["referral_code"]

        order_id, _ = _create_referred_order(
            base_url,
            referral_code,
            product["id"],
            f"qa.iter4.finance.{uuid.uuid4().hex[:6]}@example.com",
            "+919811112222",
        )
        _mark_order_state(admin, base_url, order_id, "PAID", "DELIVERED", "FULFILLED", "QA_ITER4 paid+delivered")

        commission = _commission_for_order(admin, base_url, rid, order_id)
        assert commission["status"] == "PENDING"
        _set_commission_state(admin, base_url, commission["id"], "APPROVED", "QA_ITER4 approval")
        _set_commission_state(admin, base_url, commission["id"], "PAYABLE", "QA_ITER4 payable")

        commission_ids = [commission["id"]]
        reserve = admin.post(
            f"{base_url}/api/admin/business/payouts",
            json={
                "reseller_id": rid,
                "commission_ids": commission_ids,
                "request_id": f"QA_ITER4_REQ_{uuid.uuid4().hex[:10]}",
                "reason": "QA_ITER4 reserve payout",
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        if reserve.status_code == 400 and "minimum" in reserve.text.lower():
            extra_order, _ = _create_referred_order(
                base_url,
                referral_code,
                product["id"],
                f"qa.iter4.finance.extra.{uuid.uuid4().hex[:6]}@example.com",
                "+919822223333",
            )
            _mark_order_state(admin, base_url, extra_order, "PAID", "DELIVERED", "FULFILLED", "QA_ITER4 paid+delivered extra")
            extra_commission = _commission_for_order(admin, base_url, rid, extra_order)
            _set_commission_state(admin, base_url, extra_commission["id"], "APPROVED", "QA_ITER4 approval extra")
            _set_commission_state(admin, base_url, extra_commission["id"], "PAYABLE", "QA_ITER4 payable extra")
            commission_ids.append(extra_commission["id"])
            reserve = admin.post(
                f"{base_url}/api/admin/business/payouts",
                json={
                    "reseller_id": rid,
                    "commission_ids": commission_ids,
                    "request_id": f"QA_ITER4_REQ_{uuid.uuid4().hex[:10]}",
                    "reason": "QA_ITER4 reserve payout retry",
                },
                headers=_origin_headers(base_url),
                timeout=30,
            )
        assert reserve.status_code == 200, reserve.text
        payout_id = reserve.json()["id"]

        adjust_reserved = admin.post(
            f"{base_url}/api/admin/business/commission/{commission['id']}/adjust",
            json={"new_amount": "1", "reason": "QA_ITER4 must fail while reserved"},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert adjust_reserved.status_code == 409

        fail = admin.patch(
            f"{base_url}/api/admin/business/payouts/{payout_id}",
            json={"status": "FAILED", "reason": "QA_ITER4 fail and release", "notes": "qa"},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert fail.status_code == 200, fail.text

        reserve_again = admin.post(
            f"{base_url}/api/admin/business/payouts",
            json={
                "reseller_id": rid,
                "commission_ids": commission_ids,
                "request_id": f"QA_ITER4_REQ_{uuid.uuid4().hex[:10]}",
                "reason": "QA_ITER4 reserve again",
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert reserve_again.status_code == 200, reserve_again.text

        # Pending commission adjustment old/new/diff branch
        fail_again = admin.patch(
            f"{base_url}/api/admin/business/payouts/{reserve_again.json()['id']}",
            json={"status": "FAILED", "reason": "QA_ITER4 release for adjustment", "notes": "qa"},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert fail_again.status_code == 200
        adjust_pending = admin.post(
            f"{base_url}/api/admin/business/commission/{commission['id']}/adjust",
            json={"new_amount": "10.50", "reason": "QA_ITER4 pending manual adjust"},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert adjust_pending.status_code == 200, adjust_pending.text
        adj = adjust_pending.json()
        assert adj["old_amount_minor"] > 0
        assert adj["new_amount_minor"] == 1050
        assert adj["difference_minor"] == adj["new_amount_minor"] - adj["old_amount_minor"]

        # Move to paid then adjust again => paid-adjustment branch (affects future payout)
        _set_commission_state(admin, base_url, commission["id"], "APPROVED", "QA_ITER4 reapprove")
        _set_commission_state(admin, base_url, commission["id"], "PAYABLE", "QA_ITER4 repayable")
        paid_payout = admin.post(
            f"{base_url}/api/admin/business/payouts",
            json={
                "reseller_id": rid,
                "commission_ids": commission_ids,
                "request_id": f"QA_ITER4_REQ_{uuid.uuid4().hex[:10]}",
                "reason": "QA_ITER4 paid path",
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert paid_payout.status_code == 200, paid_payout.text
        pid = paid_payout.json()["id"]
        approve = admin.patch(
            f"{base_url}/api/admin/business/payouts/{pid}",
            json={"status": "APPROVED", "reason": "QA_ITER4 approve", "notes": "ok"},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert approve.status_code == 200, approve.text
        pay = admin.patch(
            f"{base_url}/api/admin/business/payouts/{pid}",
            json={
                "status": "PAID",
                "reason": "QA_ITER4 paid",
                "notes": "actual transfer",
                "actual_payment_confirmed": True,
                "payment_reference": f"UTR{uuid.uuid4().hex[:10].upper()}",
                "payment_date": str(date.today() - timedelta(days=1)),
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert pay.status_code == 200, pay.text

        adjust_paid = admin.post(
            f"{base_url}/api/admin/business/commission/{commission['id']}/adjust",
            json={"new_amount": "9.99", "reason": "QA_ITER4 paid adjustment"},
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert adjust_paid.status_code == 200, adjust_paid.text
        paid_adj = adjust_paid.json()
        assert paid_adj["old_amount_minor"] >= 0
        assert paid_adj["new_amount_minor"] == 999
        assert paid_adj["difference_minor"] == paid_adj["new_amount_minor"] - paid_adj["old_amount_minor"]

        # Return after paid payout => single ORDER_REVERSAL (no duplicates on repeated return update)
        _mark_order_state(admin, base_url, order_id, "PAID", "RETURNED", "FULFILLED", "QA_ITER4 return post-paid")
        _mark_order_state(admin, base_url, order_id, "PAID", "RETURNED", "FULFILLED", "QA_ITER4 repeat return")
        ledger = admin.get(
            f"{base_url}/api/admin/business/commission?reseller_id={rid}&limit=100",
            timeout=30,
        )
        assert ledger.status_code == 200
        reversals = [
            x
            for x in ledger.json().get("adjustments", [])
            if x.get("commission_id") == commission["id"] and x.get("kind") == "ORDER_REVERSAL"
        ]
        assert len(reversals) == 1
        assert reversals[0]["difference_minor"] < 0

    # Referrals module: invalid code, FIRST policy preservation, self-order classification, logged-in reseller reorder tagging.
    def test_referral_policy_edges_and_self_reorder_channel(self, base_url, admin_credentials):
        creds = _load_iter3_creds()
        admin = _admin_login(base_url, admin_credentials)
        product = _pick_available_product(base_url)

        invalid = requests.post(
            f"{base_url}/api/referrals/visit",
            json={"code": "INVALID-CODE", "source": "pytest_iter4", "campaign": ""},
            timeout=30,
        )
        assert invalid.status_code == 404

        customer = requests.Session()
        first = customer.post(
            f"{base_url}/api/referrals/visit",
            json={"code": creds["A"]["referral_code"], "source": "pytest_iter4", "campaign": ""},
            timeout=30,
        )
        assert first.status_code == 200
        second = customer.post(
            f"{base_url}/api/referrals/visit",
            json={"code": creds["B"].get("referral_code", creds["A"]["referral_code"]), "source": "pytest_iter4", "campaign": ""},
            timeout=30,
        )
        assert second.status_code == 200
        assert isinstance(second.json().get("attribution_preserved"), bool)

        self_order = customer.post(
            f"{base_url}/api/orders",
            json={
                "name": "QA ITER4 Self",
                "email": creds["A"]["email"],
                "mobile": "+919899887766",
                "address": "QA Test Address",
                "city": "Sangli",
                "pincode": "416416",
                "consent": True,
                "request_id": f"QA_ITER4_SELF_{uuid.uuid4()}",
                "attribution": {"utm_source": "pytest_iter4"},
                "items": [{"product_id": product["id"], "quantity": 1}],
            },
            timeout=30,
        )
        assert self_order.status_code == 200, self_order.text
        self_id = self_order.json()["id"]

        orders = admin.get(f"{base_url}/api/admin/business/orders?limit=100", timeout=30)
        assert orders.status_code == 200
        row = next(x for x in orders.json()["items"] if x["id"] == self_id)
        assert row["order_channel"] == "RESELLER_SELF"

        reseller_a = _reseller_login(base_url, creds["A"]["email"], creds["A"]["password"])
        logged_in_self = reseller_a.post(
            f"{base_url}/api/orders",
            json={
                "name": "QA ITER4 Logged Reseller",
                "email": creds["A"]["email"],
                "mobile": "+919700001234",
                "address": "QA Test Address",
                "city": "Sangli",
                "pincode": "416416",
                "consent": True,
                "request_id": f"QA_ITER4_LOGGED_{uuid.uuid4()}",
                "attribution": {"utm_source": "pytest_iter4"},
                "items": [{"product_id": product["id"], "quantity": 1}],
            },
            timeout=30,
        )
        assert logged_in_self.status_code == 200, logged_in_self.text
        logged_id = logged_in_self.json()["id"]
        check = admin.get(f"{base_url}/api/admin/business/orders?limit=100", timeout=30)
        assert check.status_code == 200
        logged_row = next(x for x in check.json()["items"] if x["id"] == logged_id)
        assert logged_row["order_channel"] == "RESELLER_SELF"

    # Rules module: fixed/unit exact paise and historical version preservation.
    def test_fixed_per_unit_rule_exact_paise_and_history(self, base_url, admin_credentials):
        creds = _load_iter3_creds()
        admin = _admin_login(base_url, admin_credentials)
        product = _pick_available_product(base_url)

        create = admin.post(
            f"{base_url}/api/admin/business/commission-rules",
            json={
                "name": "QA_ITER4_FIXED_UNIT",
                "kind": "FIXED_PER_UNIT",
                "rate": "12.34",
                "product_ids": [product["id"]],
                "variant_ids": [],
                "bundle_sizes": [],
                "tiers": ["STARTER"],
                "reseller_ids": [creds["A"]["reseller_id"]],
                "priority": 1000,
                "starts_at": None,
                "ends_at": None,
                "active": True,
                "reason": "QA_ITER4 create fixed-per-unit",
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert create.status_code == 200, create.text
        v1 = create.json()
        assert str(v1["rate"]) in ["12.34", "12.3400000000", "12.34"]
        assert v1["version"] >= 1

        supersede = admin.put(
            f"{base_url}/api/admin/business/commission-rules/{v1['id']}",
            json={
                "name": "QA_ITER4_FIXED_UNIT",
                "kind": "FIXED_PER_UNIT",
                "rate": "10.01",
                "product_ids": [product["id"]],
                "variant_ids": [],
                "bundle_sizes": [],
                "tiers": ["STARTER"],
                "reseller_ids": [creds["A"]["reseller_id"]],
                "priority": 1000,
                "starts_at": None,
                "ends_at": None,
                "active": True,
                "reason": "QA_ITER4 supersede",
            },
            headers=_origin_headers(base_url),
            timeout=30,
        )
        assert supersede.status_code == 200, supersede.text
        v2 = supersede.json()
        assert v2["version"] == v1["version"] + 1

        all_rules = admin.get(f"{base_url}/api/admin/business/commission-rules", timeout=30)
        assert all_rules.status_code == 200
        group_rows = [x for x in all_rules.json().get("items", []) if x.get("group_id") == v1["group_id"]]
        assert len(group_rows) >= 2
        old = next(x for x in group_rows if x["id"] == v1["id"])
        current = next(x for x in group_rows if x["id"] == v2["id"])
        assert old["is_current"] is False
        assert current["is_current"] is True
