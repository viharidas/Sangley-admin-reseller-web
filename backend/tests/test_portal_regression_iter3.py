"""Portal reseller/admin/finance regression coverage for QA iteration 3."""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def _origin_headers(base_url: str) -> dict[str, str]:
    return {"Origin": base_url, "Content-Type": "application/json"}


def _new_reseller_payload(tag: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    email = f"qa_portal_{tag}_{suffix}@example.com"
    password = f"QA_PORTAL_{tag}_{suffix}123"
    digits = "6" + "".join(str((int(c, 16) % 10)) for c in uuid.uuid4().hex[:9])
    mobile = f"+91{digits}"
    return {
        "full_name": f"QA_PORTAL_{tag}",
        "email": email,
        "password": password,
        "mobile": mobile,
        "city": "Sangli",
        "address": "QA Portal Street",
        "community_type": "Friends",
        "network_size": 25,
        "whatsapp": mobile,
        "referral_source": "pytest_iter3",
        "pan": "ABCDE1234F",
        "gst": "27ABCDE1234F1Z5",
        "account_name": f"QA PORTAL {tag}",
        "account_number": "123456789012",
        "ifsc": "HDFC0001234",
        "terms_accepted": True,
    }


def _admin_login(admin_session: requests.Session, base_url: str, admin_credentials: dict):
    login = admin_session.post(
        f"{base_url}/api/auth/login",
        json=admin_credentials,
        headers=_origin_headers(base_url),
    )
    assert login.status_code == 200, login.text
    data = login.json()
    assert data["role"] == "admin"


def _reseller_login(reseller_session: requests.Session, base_url: str, email: str, password: str):
    login = reseller_session.post(
        f"{base_url}/api/reseller/auth/login",
        json={"email": email, "password": password},
        headers=_origin_headers(base_url),
    )
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["user"]["email"] == email.lower()
    return body


def _fetch_first_product(base_url: str) -> dict:
    r = requests.get(f"{base_url}/api/products", timeout=25)
    assert r.status_code == 200
    products = r.json()
    assert len(products) >= 4
    picked = next((p for p in products if p.get("available") and float(p.get("price", 0)) == 149), products[0])
    return picked


def test_portal_business_workflow_regression(base_url, admin_credentials):
    """Auth, RBAC, referrals, commission, payouts, and idempotency critical path."""
    # Public commerce regression: storefront data and quote continue working.
    product = _fetch_first_product(base_url)
    quote = requests.post(
        f"{base_url}/api/cart/quote",
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
        timeout=25,
    )
    assert quote.status_code == 200
    quote_data = quote.json()
    assert quote_data["checkout_mode"] == "enquiry"
    assert quote_data["items"][0]["product_id"] == product["id"]

    # OTP/reset are intentionally unavailable (503) without providers.
    otp_send = requests.post(
        f"{base_url}/api/reseller/auth/otp/send",
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert otp_send.status_code == 503
    assert "unavailable" in otp_send.json().get("detail", "").lower()
    reset = requests.post(
        f"{base_url}/api/reseller/auth/forgot-password",
        json={"email": "qa@example.com"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert reset.status_code == 503
    assert "no email has been sent" in reset.json().get("detail", "").lower()

    # Register two QA reseller applications.
    reseller_a = _new_reseller_payload("A")
    reseller_b = _new_reseller_payload("B")
    a_register_sess = requests.Session()
    b_register_sess = requests.Session()
    a_reg = a_register_sess.post(
        f"{base_url}/api/reseller/auth/register",
        json=reseller_a,
        headers=_origin_headers(base_url),
        timeout=25,
    )
    b_reg = b_register_sess.post(
        f"{base_url}/api/reseller/auth/register",
        json=reseller_b,
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert a_reg.status_code == 200, a_reg.text
    assert b_reg.status_code == 200, b_reg.text
    a_profile = a_reg.json()["profile"]
    b_profile = b_reg.json()["profile"]
    assert a_profile["status"] == "PENDING"
    assert b_profile["status"] == "PENDING"
    assert a_profile["payout_details"]["account_number"].startswith("••••")

    # Pending accounts cannot access approved-only reseller API.
    pending_access = a_register_sess.get(f"{base_url}/api/reseller/dashboard", timeout=25)
    assert pending_access.status_code == 403

    # Admin approval creates reseller number and referral code.
    admin_session = requests.Session()
    _admin_login(admin_session, base_url, admin_credentials)
    list_resellers = admin_session.get(f"{base_url}/api/admin/business/resellers?limit=100", timeout=25)
    assert list_resellers.status_code == 200
    rows = list_resellers.json()["items"]
    row_a = next(r for r in rows if r["email"] == reseller_a["email"].lower())
    row_b = next(r for r in rows if r["email"] == reseller_b["email"].lower())

    approve_payload = {"status": "APPROVED", "tier": "STARTER", "reason": "QA_PORTAL approval"}
    approve_a = admin_session.patch(
        f"{base_url}/api/admin/business/resellers/{row_a['id']}/status",
        json=approve_payload,
        headers=_origin_headers(base_url),
        timeout=25,
    )
    approve_b = admin_session.patch(
        f"{base_url}/api/admin/business/resellers/{row_b['id']}/status",
        json=approve_payload,
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert approve_a.status_code == 200, approve_a.text
    assert approve_b.status_code == 200, approve_b.text
    approved_a = approve_a.json()
    approved_b = approve_b.json()
    assert approved_a["reseller_number"].startswith("SGR")
    assert approved_b["reseller_number"].startswith("SGR")
    assert approved_a["referral_code"] != approved_b["referral_code"]

    # Admin APIs reject unauthenticated and reseller-authenticated requests.
    unauth_admin = requests.get(f"{base_url}/api/admin/business/dashboard", timeout=25)
    assert unauth_admin.status_code == 401
    reseller_a_sess = requests.Session()
    _reseller_login(reseller_a_sess, base_url, reseller_a["email"], reseller_a["password"])
    reseller_on_admin = reseller_a_sess.get(f"{base_url}/api/admin/business/dashboard", timeout=25)
    assert reseller_on_admin.status_code == 401

    # Sensitive fields remain masked for reseller profile and extra fields are rejected.
    a_profile_now = reseller_a_sess.get(f"{base_url}/api/reseller/profile", timeout=25)
    assert a_profile_now.status_code == 200
    profile_body = a_profile_now.json()
    assert profile_body["payout_details"]["pan"].startswith("••••")
    invalid_privileged_patch = reseller_a_sess.patch(
        f"{base_url}/api/reseller/profile",
        json={"status": "APPROVED"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert invalid_privileged_patch.status_code == 422

    # Build test rule: 10% then supersede with 12%; first order keeps snapshot at 10%.
    rule_10 = {
        "name": "QA_PORTAL_10PCT",
        "kind": "PERCENTAGE",
        "rate": "10",
        "product_ids": [product["id"]],
        "variant_ids": [],
        "bundle_sizes": [],
        "tiers": ["STARTER"],
        "reseller_ids": [],
        "priority": 99,
        "starts_at": None,
        "ends_at": None,
        "active": True,
        "reason": "QA_PORTAL test rule"
    }
    created_rule = admin_session.post(
        f"{base_url}/api/admin/business/commission-rules",
        json=rule_10,
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert created_rule.status_code == 200, created_rule.text
    rule_v1 = created_rule.json()
    assert str(rule_v1["rate"]) in ["10", "10.0"]

    # Customer browser visits referral link and then creates enquiry order (idempotent).
    customer = requests.Session()
    referral_visit = customer.post(
        f"{base_url}/api/referrals/visit",
        json={"code": approved_a["referral_code"], "source": "pytest_iter3", "campaign": ""},
        timeout=25,
    )
    assert referral_visit.status_code == 200, referral_visit.text
    assert referral_visit.json()["valid"] is True
    assert "sangley_referral" in customer.cookies.get_dict()

    order_request_id = f"QA_PORTAL_ORDER_{uuid.uuid4()}"
    order_body = {
        "name": "QA PORTAL Customer",
        "email": f"qa.portal.customer.{uuid.uuid4().hex[:6]}@example.com",
        "mobile": "+919812345678",
        "address": "Sangli Test Address",
        "city": "Sangli",
        "pincode": "416416",
        "consent": True,
        "request_id": order_request_id,
        "attribution": {"utm_source": "pytest"},
        "items": [{"product_id": product["id"], "quantity": 1}],
    }
    order1 = customer.post(f"{base_url}/api/orders", json=order_body, timeout=25)
    order2 = customer.post(f"{base_url}/api/orders", json=order_body, timeout=25)
    assert order1.status_code == 200
    assert order2.status_code == 200
    order_id = order1.json()["id"]
    assert order2.json()["id"] == order_id

    # No commission ledger before payment confirmation.
    comm_before = admin_session.get(
        f"{base_url}/api/admin/business/commission?reseller_id={row_a['id']}", timeout=25
    )
    assert comm_before.status_code == 200
    assert all(c["order_id"] != order_id for c in comm_before.json()["items"])

    # Supersede rule to 12% for future orders.
    rule_12 = {**rule_10, "rate": "12", "reason": "QA_PORTAL supersede to 12"}
    update_rule = admin_session.put(
        f"{base_url}/api/admin/business/commission-rules/{rule_v1['id']}",
        json=rule_12,
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert update_rule.status_code == 200, update_rule.text
    assert str(update_rule.json()["rate"]) in ["12", "12.0"]

    # Mark order paid (still not delivered), commission should be created as PENDING.
    mark_paid = admin_session.patch(
        f"{base_url}/api/admin/business/orders/{order_id}",
        json={
            "payment_status": "PAID",
            "delivery_status": "NOT_SHIPPED",
            "status": "CONFIRMED",
            "payment_reference": f"QA_PAY_{uuid.uuid4().hex[:6]}",
            "reason": "QA paid confirmation",
        },
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert mark_paid.status_code == 200, mark_paid.text
    assert mark_paid.json()["payment_status"] == "PAID"

    comm_after_paid = admin_session.get(
        f"{base_url}/api/admin/business/commission?reseller_id={row_a['id']}", timeout=25
    )
    assert comm_after_paid.status_code == 200
    commission_row = next(c for c in comm_after_paid.json()["items"] if c["order_id"] == order_id)
    assert commission_row["status"] == "PENDING"
    assert commission_row["amount_minor"] == 1490

    # Eligibility approval blocked before delivery.
    approve_before_delivery = admin_session.patch(
        f"{base_url}/api/admin/business/commission/{commission_row['id']}/status",
        json={"status": "APPROVED", "reason": "QA pre-delivery approve should fail"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert approve_before_delivery.status_code == 409

    # Once delivered: PENDING -> APPROVED -> PAYABLE.
    mark_delivered = admin_session.patch(
        f"{base_url}/api/admin/business/orders/{order_id}",
        json={
            "payment_status": "PAID",
            "delivery_status": "DELIVERED",
            "status": "FULFILLED",
            "payment_reference": mark_paid.json()["payment_reference"],
            "reason": "QA delivered",
        },
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert mark_delivered.status_code == 200
    approve = admin_session.patch(
        f"{base_url}/api/admin/business/commission/{commission_row['id']}/status",
        json={"status": "APPROVED", "reason": "QA approve after delivery"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    payable = admin_session.patch(
        f"{base_url}/api/admin/business/commission/{commission_row['id']}/status",
        json={"status": "PAYABLE", "reason": "QA payable step"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert approve.status_code == 200, approve.text
    assert payable.status_code == 200, payable.text
    assert payable.json()["status"] == "PAYABLE"

    # Payout create and transition controls.
    payout_request_id = f"QA_REQ_{uuid.uuid4().hex[:10]}"
    payout_create = admin_session.post(
        f"{base_url}/api/admin/business/payouts",
        json={
            "reseller_id": row_a["id"],
            "commission_ids": [commission_row["id"]],
            "request_id": payout_request_id,
            "reason": "QA payout prepare",
        },
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert payout_create.status_code == 200, payout_create.text
    payout = payout_create.json()
    assert payout["status"] == "PENDING"
    assert payout["reservation_complete"] is True

    duplicate_commission_select = admin_session.post(
        f"{base_url}/api/admin/business/payouts",
        json={
            "reseller_id": row_a["id"],
            "commission_ids": [commission_row["id"], commission_row["id"]],
            "request_id": f"QA_REQ_{uuid.uuid4().hex[:10]}",
            "reason": "QA invalid duplicate commission IDs",
        },
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert duplicate_commission_select.status_code == 400

    approve_payout = admin_session.patch(
        f"{base_url}/api/admin/business/payouts/{payout['id']}",
        json={"status": "APPROVED", "reason": "QA review pass", "notes": "checked"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert approve_payout.status_code == 200

    paid_without_required_fields = admin_session.patch(
        f"{base_url}/api/admin/business/payouts/{payout['id']}",
        json={"status": "PAID", "reason": "QA missing payment inputs", "notes": "x"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert paid_without_required_fields.status_code == 422

    paid_ok = admin_session.patch(
        f"{base_url}/api/admin/business/payouts/{payout['id']}",
        json={
            "status": "PAID",
            "reason": "QA manual payment recorded",
            "notes": "manual transfer recorded",
            "actual_payment_confirmed": True,
            "payment_reference": f"UTR-{uuid.uuid4().hex[:10].upper()}",
            "payment_date": str(date.today() - timedelta(days=1)),
        },
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert paid_ok.status_code == 200, paid_ok.text
    assert paid_ok.json()["status"] == "PAID"

    # IDOR check: reseller A cannot read reseller B ticket.
    reseller_b_sess = requests.Session()
    _reseller_login(reseller_b_sess, base_url, reseller_b["email"], reseller_b["password"])
    ticket = reseller_b_sess.post(
        f"{base_url}/api/reseller/support",
        json={"subject": "QA Ticket", "category": "OTHER", "message": "QA_PORTAL message", "attachment_ids": []},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert ticket.status_code == 200, ticket.text
    tid = ticket.json()["id"]
    idor_ticket = reseller_a_sess.post(
        f"{base_url}/api/reseller/support/{tid}/reply",
        json={"message": "IDOR attempt"},
        headers=_origin_headers(base_url),
        timeout=25,
    )
    assert idor_ticket.status_code == 404

    # Keep fixture context visible in test output for credentials/report handoff.
    print(
        f"QA_PORTAL_FIXTURE reseller_a_email={reseller_a['email']} password={reseller_a['password']} "
        f"reseller_b_email={reseller_b['email']} password={reseller_b['password']} "
        f"reseller_a_id={row_a['id']} reseller_b_id={row_b['id']} order_id={order_id} "
        f"commission_id={commission_row['id']} payout_id={payout['id']} referral_code={approved_a['referral_code']}"
    )
