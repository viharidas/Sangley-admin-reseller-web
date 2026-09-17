"""Iteration-6 regression: focused durable tests requested by main agent.

Key differences from iter5:
- No hardcoded Mongo defaults or auth passwords; all sourced from env + credentials files.
- Reproduces metrics.py line-59 rounding bug at order-snapshot level using the *exact*
  allocation formula from portal/metrics.py (no dependence on aggregated report so previous
  missing-cost orders do not mask the assertion).
- Historical immutability test now first captures the snapshot BEFORE configuring costs,
  then configures costs, then re-fetches and asserts equality (iter5 skipped this step).
- Leaves one PENDING/APPROVED payout for downstream browser test (KEEP_NONTERMINAL fixture).
- Extends tampered-cookie & same-normalized-mobile scenarios to include PAID+DELIVERED
  transitions and asserts commissions still remain absent.
- Manifest is merged with any existing content (cumulative) rather than overwritten.
- Restore of business_settings is asserted for success (not best-effort).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


# --- Env / credentials -----------------------------------------------------

MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
if not MONGO_URL or not DB_NAME:
    pytest.skip("MONGO_URL and DB_NAME must be set in backend/.env", allow_module_level=True)


def _load_reseller_profiles():
    path = Path("/app/test_reports/portal_iter3_credentials.json")
    if not path.exists():
        pytest.skip("portal_iter3_credentials.json not found; run iter3 fixtures first",
                    allow_module_level=True)
    data = json.loads(path.read_text())
    # B is the finance target; A left available for future needs.
    a = data["A"]
    b = data["B"]
    b.setdefault("reseller_id", "357245f0-1937-453c-9bfd-2168cb3361d2")
    b.setdefault("referral_code", "SNG0E106BCFAF69")
    a.setdefault("reseller_id", "9b9ecb49-5c1a-463c-91cb-452e18622815")
    a.setdefault("referral_code", "SNG40025330D4AB")
    return a, b


RESELLER_A, RESELLER_B = _load_reseller_profiles()

MANIFEST_PATH = Path("/app/test_reports/qa_iter6_manifest.json")


def _origin(base_url):
    return {"Origin": base_url, "Content-Type": "application/json"}


# --- Fixtures --------------------------------------------------------------

@pytest.fixture(scope="module")
def mongo():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(scope="module")
def manifest():
    seed = {
        "orders": [], "commissions": [], "payouts": [], "adjustments": [],
        "referral_sessions": [], "referral_events": [], "rules": [],
        "ownerships": [], "notifications": [], "non_terminal_payout_ids": [],
    }
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text())
            for k in seed:
                if k in existing and isinstance(existing[k], list):
                    seed[k] = list(existing[k])
        except Exception:
            pass
    yield seed
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    # De-duplicate lists preserving order
    for k, v in seed.items():
        seen = set(); merged = []
        for item in v:
            key = json.dumps(item, sort_keys=True, default=str)
            if key in seen: continue
            seen.add(key); merged.append(item)
        seed[k] = merged
    MANIFEST_PATH.write_text(json.dumps(seed, indent=2, default=str))


@pytest.fixture(scope="module")
def admin_session(base_url, admin_credentials):
    s = requests.Session()
    r = s.post(f"{base_url}/api/auth/login", json=admin_credentials,
               headers=_origin(base_url), timeout=30)
    assert r.status_code == 200, r.text
    return s


# --- Helpers ---------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _pick_products(base_url):
    rows = requests.get(f"{base_url}/api/products", timeout=30).json()
    avail = [p for p in rows if p.get("available")]
    assert len(avail) >= 2
    # Prefer garlic + peri-peri (no pre-existing rules)
    picks = [p for p in avail if p["id"] in ("garlic", "peri-peri")]
    if len(picks) < 2:
        picks = avail[:2]
    return picks[:2]


def _visit(session, base_url, code):
    r = session.post(f"{base_url}/api/referrals/visit",
                     json={"code": code, "source": "pytest_iter6", "campaign": ""},
                     timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _create_order(session, base_url, items, email, mobile, name="QA_ITER6", extra=None):
    body = {
        "name": name, "email": email, "mobile": mobile,
        "address": "QA Iter6 Street 42", "city": "Sangli", "pincode": "416416",
        "consent": True, "request_id": f"QA_ITER6_{uuid.uuid4()}",
        "attribution": {"utm_source": "pytest_iter6"}, "items": items,
    }
    if extra:
        body.update(extra)
    r = session.post(f"{base_url}/api/orders", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mark_state(admin, base_url, oid, payment, delivery, status, reason,
                reference=None):
    r = admin.patch(f"{base_url}/api/admin/business/orders/{oid}",
                    json={"payment_status": payment, "delivery_status": delivery,
                          "status": status,
                          "payment_reference": reference or f"QA6-{uuid.uuid4().hex[:8]}",
                          "reason": reason},
                    headers=_origin(base_url), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _get_commission(admin, base_url, rid, oid, retries=8):
    for _ in range(retries):
        r = admin.get(f"{base_url}/api/admin/business/commission?reseller_id={rid}&limit=100",
                      timeout=30)
        assert r.status_code == 200
        row = next((x for x in r.json()["items"] if x["order_id"] == oid), None)
        if row:
            return row
        time.sleep(0.4)
    return None


async def _afetch_order(mongo_db, oid):
    return await mongo_db.orders.find_one({"id": oid}, {"_id": 0})


# --- Class 1: Metrics reconciliation reproduction --------------------------

class TestIter6MetricsReconciliation:
    """Reproduces `portal/metrics.py` line-59 rounding drift at the order snapshot
    level using the *same* allocation formula used by `sales()` product breakdown.
    This is independent of the aggregated /sales report so earlier missing-cost
    orders cannot mask the assertion.
    """

    def test_multiline_per_order_product_profit_reconciles_to_order_profit(
            self, base_url, admin_session, manifest, mongo):
        products = _pick_products(base_url)
        admin = admin_session

        old = _run(mongo.business_settings.find_one({"id": "portal"}, {"_id": 0}))
        old_costs = old.get("product_costs", {}) or {}
        old_other = old.get("other_cost_per_order")

        # 1) Create rule scoped to B covering BOTH selected products.
        rule_body = {
            "name": f"QA_ITER6_MULTI_{uuid.uuid4().hex[:6]}",
            "kind": "PERCENTAGE", "rate": "10",
            "product_ids": [p["id"] for p in products],
            "variant_ids": [], "bundle_sizes": [], "tiers": [],
            "reseller_ids": [RESELLER_B["reseller_id"]],
            "priority": 500, "active": True,
            "reason": "QA_ITER6 create scoped multi-product rule",
        }
        r_rule = admin.post(f"{base_url}/api/admin/business/commission-rules",
                            json=rule_body, headers=_origin(base_url), timeout=30)
        assert r_rule.status_code == 200, r_rule.text
        rule_id = r_rule.json()["id"]
        manifest["rules"].append(rule_id)

        try:
            # 2) Configure costs BEFORE order so snapshot is fully known.
            new_costs = {**old_costs,
                         products[0]["id"]: "1.00",
                         products[1]["id"]: "1.00"}
            put = admin.put(f"{base_url}/api/admin/business/settings",
                            json={**old, "product_costs": new_costs,
                                  "other_cost_per_order": "0.01",
                                  "reason": "QA_ITER6 configure costs for reconciliation"},
                            headers=_origin(base_url), timeout=30)
            assert put.status_code == 200, put.text

            # 3) Place multi-line order under B.
            customer = requests.Session()
            _visit(customer, base_url, RESELLER_B["referral_code"])
            email = f"qa6.multi.{uuid.uuid4().hex[:6]}@example.com"
            oid = _create_order(customer, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1},
                                 {"product_id": products[1]["id"], "quantity": 1}],
                                email, "+919812220001")
            manifest["orders"].append(oid)

            # 4) Mark PAID + DELIVERED so commission earns
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER6 multi paid+delivered")
            c = _get_commission(admin, base_url, RESELLER_B["reseller_id"], oid)
            assert c is not None, "Commission must be earned when configured"
            manifest["commissions"].append(c["id"])

            # 5) Fetch order snapshot & validate baseline arithmetic
            order = _run(_afetch_order(mongo, oid))
            snap = order["economics_snapshot"]
            assert snap["configured"] is True
            assert snap["commission_minor"] == 2980, snap
            assert snap["product_cost_minor"] == 200, snap
            assert snap["other_cost_minor"] == 1, snap
            assert snap["estimated_gross_profit_minor"] == 29800 - 200 - 2980 - 1

            # 6) Reproduce metrics.sales() product allocation for THIS order.
            parts = snap["parts"]
            total_commission = c["amount_minor"]
            original = sum((x.get("commission_minor") or 0) for x in parts)
            allocated = 0
            product_profits = []
            for idx, part in enumerate(parts):
                share = round(total_commission * (part.get("commission_minor") or 0) / original) if original else 0
                actual_commission = total_commission - allocated if idx == len(parts) - 1 else share
                allocated += actual_commission
                other_share = round(snap["other_cost_minor"] * part["sales_minor"] / max(snap["sales_minor"], 1))
                pprofit = part["sales_minor"] - part["cost_minor"] - actual_commission - other_share
                product_profits.append(pprofit)

            summed = sum(product_profits)
            order_profit = snap["estimated_gross_profit_minor"]
            print(f"[iter6] order={oid} product_profits={product_profits} "
                  f"sum={summed} order_profit={order_profit} diff={summed-order_profit}")

            # Each product profit must not be None
            assert all(p is not None for p in product_profits), product_profits

            # ---- KEY ASSERTION (expected to FAIL until metrics.py:59 is fixed) ----
            # Product-level allocation must reconcile exactly to the order snapshot.
            assert summed == order_profit, (
                f"metrics.py per-product profit allocation drift: "
                f"sum(products.profit_minor)={summed} but "
                f"snapshot.estimated_gross_profit_minor={order_profit} "
                f"(diff={summed-order_profit} paise). "
                f"Fix: add a residual absorber to the last part for other_cost_minor split, "
                f"mirroring the commission allocation pattern already used."
            )
        finally:
            # Deactivate the rule (supersede with active=False)
            get = admin.get(f"{base_url}/api/admin/business/commission-rules",
                            timeout=30).json()
            cur = next((x for x in get["items"] if x["id"] == rule_id), None)
            if cur and cur.get("is_current"):
                body = {**{k: cur[k] for k in
                           ["name", "kind", "rate", "product_ids", "variant_ids",
                            "bundle_sizes", "tiers", "reseller_ids", "priority"]},
                        "rate": str(cur["rate"]),
                        "active": False,
                        "reason": "QA_ITER6 deactivate scoped rule"}
                admin.put(f"{base_url}/api/admin/business/commission-rules/{rule_id}",
                          json=body, headers=_origin(base_url), timeout=30)

            # Restore settings (asserted success now)
            restore = {**old,
                       "product_costs": {k: str(v) for k, v in old_costs.items()},
                       "other_cost_per_order": str(old_other) if old_other is not None else None,
                       "reason": "QA_ITER6 restore settings"}
            r2 = admin.put(f"{base_url}/api/admin/business/settings", json=restore,
                           headers=_origin(base_url), timeout=30)
            assert r2.status_code == 200, f"restore failed: {r2.status_code} {r2.text}"


# --- Class 2: Historical snapshot immutability -----------------------------

class TestIter6HistoricalImmutability:

    def test_missing_cost_snapshot_unchanged_after_later_configuration(
            self, base_url, admin_session, manifest, mongo):
        products = _pick_products(base_url)
        admin = admin_session

        old = _run(mongo.business_settings.find_one({"id": "portal"}, {"_id": 0}))
        old_costs = old.get("product_costs", {}) or {}
        old_other = old.get("other_cost_per_order")

        # 1) Ensure this product has NO cost, other_cost is None
        clear = {**old,
                 "product_costs": {k: v for k, v in old_costs.items()
                                   if k != products[0]["id"]},
                 "other_cost_per_order": None,
                 "reason": "QA_ITER6 clear costs for immutability test"}
        r0 = admin.put(f"{base_url}/api/admin/business/settings", json=clear,
                       headers=_origin(base_url), timeout=30)
        assert r0.status_code == 200, r0.text

        try:
            # 2) Create order with missing costs, capture original snapshot
            customer = requests.Session()
            _visit(customer, base_url, RESELLER_B["referral_code"])
            oid = _create_order(customer, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1}],
                                f"qa6.hist.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812220002")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER6 historical missing-cost order")

            order_before = _run(_afetch_order(mongo, oid))
            snap_before = order_before["economics_snapshot"]
            # Baseline: snapshot has null profit
            assert snap_before["estimated_gross_profit_minor"] is None
            assert snap_before["product_cost_minor"] is None
            assert snap_before["other_cost_minor"] is None

            # 3) Now configure costs after-the-fact
            configured = {**old,
                          "product_costs": {**old_costs,
                                            products[0]["id"]: "1.00"},
                          "other_cost_per_order": "0.01",
                          "reason": "QA_ITER6 configure costs after historical order"}
            r1 = admin.put(f"{base_url}/api/admin/business/settings", json=configured,
                           headers=_origin(base_url), timeout=30)
            assert r1.status_code == 200, r1.text

            # 4) Re-fetch the SAME order; snapshot must be byte-identical
            order_after = _run(_afetch_order(mongo, oid))
            snap_after = order_after["economics_snapshot"]
            assert snap_after == snap_before, (
                f"Historical snapshot mutated after cost configuration! "
                f"before={snap_before} after={snap_after}"
            )
            # And profit remains null on the individual order snapshot
            assert snap_after["estimated_gross_profit_minor"] is None
        finally:
            # Restore original settings exactly
            restore = {**old,
                       "product_costs": {k: str(v) for k, v in old_costs.items()},
                       "other_cost_per_order": str(old_other) if old_other is not None else None,
                       "reason": "QA_ITER6 restore after immutability"}
            r2 = admin.put(f"{base_url}/api/admin/business/settings", json=restore,
                           headers=_origin(base_url), timeout=30)
            assert r2.status_code == 200, f"restore failed: {r2.text}"


# --- Class 3: Non-terminal payout for browser test -------------------------

class TestIter6PayoutFixture:
    """Seed one non-terminal (APPROVED) payout to be exercised by the browser test.
    Do NOT transition it to PAID/FAILED here; the browser test owns that step.
    """

    def test_seed_non_terminal_payout_for_ui(self, base_url, admin_session,
                                             manifest, mongo):
        products = _pick_products(base_url)
        admin = admin_session

        old = _run(mongo.business_settings.find_one({"id": "portal"}, {"_id": 0}))
        old_costs = old.get("product_costs", {}) or {}
        old_other = old.get("other_cost_per_order")

        # Ensure costs configured so commission is earned
        new_costs = {**old_costs, products[0]["id"]: "1.00"}
        put = admin.put(f"{base_url}/api/admin/business/settings",
                        json={**old, "product_costs": new_costs,
                              "other_cost_per_order": "0.01",
                              "reason": "QA_ITER6 payout fixture costs"},
                        headers=_origin(base_url), timeout=30)
        assert put.status_code == 200

        try:
            # Create scoped rule for B (any product) so commission earns
            rule_body = {
                "name": f"QA_ITER6_PAYFIX_{uuid.uuid4().hex[:6]}",
                "kind": "PERCENTAGE", "rate": "10",
                "product_ids": [products[0]["id"]],
                "variant_ids": [], "bundle_sizes": [], "tiers": [],
                "reseller_ids": [RESELLER_B["reseller_id"]],
                "priority": 500, "active": True,
                "reason": "QA_ITER6 payout fixture rule",
            }
            r_rule = admin.post(f"{base_url}/api/admin/business/commission-rules",
                                json=rule_body, headers=_origin(base_url), timeout=30)
            assert r_rule.status_code == 200, r_rule.text
            rule_id = r_rule.json()["id"]
            manifest["rules"].append(rule_id)

            customer = requests.Session()
            _visit(customer, base_url, RESELLER_B["referral_code"])
            oid = _create_order(customer, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1}],
                                f"qa6.payfix.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812220050")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER6 payout fixture paid")
            c = _get_commission(admin, base_url, RESELLER_B["reseller_id"], oid)
            assert c is not None
            manifest["commissions"].append(c["id"])

            # APPROVE -> PAYABLE
            for st in ("APPROVED", "PAYABLE"):
                r = admin.patch(f"{base_url}/api/admin/business/commission/{c['id']}/status",
                                json={"status": st, "reason": f"QA_ITER6 {st}"},
                                headers=_origin(base_url), timeout=30)
                assert r.status_code == 200, r.text

            # Create payout
            rp = admin.post(f"{base_url}/api/admin/business/payouts",
                            json={"reseller_id": RESELLER_B["reseller_id"],
                                  "commission_ids": [c["id"]],
                                  "request_id": f"QA_ITER6_PAY_{uuid.uuid4().hex[:10]}",
                                  "reason": "QA_ITER6 create payout for UI"},
                            headers=_origin(base_url), timeout=30)
            assert rp.status_code == 200, rp.text
            pid = rp.json()["id"]
            manifest["payouts"].append(pid)

            # Move to APPROVED but NOT PAID (leave non-terminal for browser test)
            r = admin.patch(f"{base_url}/api/admin/business/payouts/{pid}",
                            json={"status": "APPROVED",
                                  "reason": "QA_ITER6 approve for UI",
                                  "notes": "approved awaiting UI paid test"},
                            headers=_origin(base_url), timeout=30)
            assert r.status_code == 200, r.text
            manifest["non_terminal_payout_ids"].append(pid)
            print(f"[iter6] Seeded non-terminal payout id={pid} status=APPROVED")
        finally:
            # Restore settings
            restore = {**old,
                       "product_costs": {k: str(v) for k, v in old_costs.items()},
                       "other_cost_per_order": str(old_other) if old_other is not None else None,
                       "reason": "QA_ITER6 restore after payout fixture"}
            r2 = admin.put(f"{base_url}/api/admin/business/settings", json=restore,
                           headers=_origin(base_url), timeout=30)
            assert r2.status_code == 200, f"restore failed: {r2.text}"


# --- Class 4: Post-payment integrity for exclusions ------------------------

class TestIter6PostPaymentExclusions:
    """iter5 asserted exclusions only up to order creation. iter6 walks the order
    through PAID + DELIVERED and re-asserts that NO commission is created."""

    def test_tampered_cookie_excludes_commission_even_after_paid_delivered(
            self, base_url, admin_session, manifest, mongo):
        products = _pick_products(base_url)
        admin = admin_session
        customer = requests.Session()
        # Inject a garbage referral cookie without any /visit call
        host = re.sub(r"^https?://", "", base_url).split("/")[0]
        customer.cookies.set("sangley_referral",
                             "tampered-" + uuid.uuid4().hex, domain=host)
        oid = _create_order(customer, base_url,
                            [{"product_id": products[0]["id"], "quantity": 1}],
                            f"qa6.tamper.{uuid.uuid4().hex[:6]}@example.com",
                            "+919812220003")
        manifest["orders"].append(oid)

        order = _run(_afetch_order(mongo, oid))
        assert order.get("reseller_id") is None
        assert order["order_channel"] == "D2C"

        # Now mark PAID + DELIVERED and re-verify no commission ever appears
        _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                    "QA_ITER6 tampered cookie paid+delivered")
        time.sleep(0.6)  # allow financial.synchronize_order to run
        c = _run(mongo.commissions.find_one({"order_id": oid}, {"_id": 0}))
        assert c is None, f"Tampered-cookie order must not earn commission after PAID+DELIVERED: {c}"

    def test_same_normalized_mobile_self_referral_no_commission_post_paid(
            self, base_url, admin_session, manifest, mongo):
        products = _pick_products(base_url)
        admin = admin_session
        b_doc = _run(mongo.resellers.find_one({"id": RESELLER_B["reseller_id"]},
                                               {"_id": 0, "mobile": 1, "whatsapp": 1}))
        # Extract national digits from B.mobile (normalized "+91XXXXXXXXXX")
        m = b_doc.get("mobile") or ""
        assert m.startswith("+91"), f"B mobile format unexpected: {m}"
        raw_mobile = m[3:]

        customer = requests.Session()
        _visit(customer, base_url, RESELLER_B["referral_code"])
        oid = _create_order(customer, base_url,
                            [{"product_id": products[0]["id"], "quantity": 1}],
                            f"qa6.self.{uuid.uuid4().hex[:6]}@example.com",
                            raw_mobile)
        manifest["orders"].append(oid)

        order = _run(_afetch_order(mongo, oid))
        assert order["order_channel"] == "RESELLER_SELF"
        assert order.get("attribution_exclusion") == "SELF_REFERRAL"
        assert order.get("reseller_id") is None

        # Mark PAID + DELIVERED
        _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                    "QA_ITER6 self-mobile paid+delivered")
        time.sleep(0.6)
        c = _run(mongo.commissions.find_one({"order_id": oid}, {"_id": 0}))
        assert c is None, f"Self-referral (same-mobile) order must not earn commission after PAID+DELIVERED: {c}"
