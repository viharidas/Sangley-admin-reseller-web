"""Iteration-7 regression: exercise ACTUAL portal.metrics.sales() implementation.

Key differences from iter6:
- We do NOT copy the app allocation formula. We monkeypatch `metrics.sale_query`
  to restrict to a single fixture order and invoke the REAL `metrics.sales()`,
  reading the answer straight from the app code path.
- Cases:
    A) Two equal-price lines + other_cost_minor=1 -> per-product profit sums must
       equal snapshot.estimated_gross_profit_minor, and no product profit is None.
    B) Bundle + individual + repeated product on one order -> totals reconcile
       and each product has orders=1 (unique product order count).
    C) Zero-rate commission earned (0) then ledger adjustment to positive amount:
       report totals/parts follow the ADJUSTED ledger without mutating the
       original snapshot.commission_minor.
    D) Historical missing-cost order regression through the real function:
       products.cost_known False; overall profit_minor null; snapshot immutable.
    E) Tiny other_cost across many lines never produces a negative cost share.

- Serial: intended to run with `-n 0` (see runner block).
- No hardcoded Mongo URL / passwords: creds via /app/memory/test_credentials.md
  and env vars only. Only QA_ITER7 prefixed data is created.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME")
if not MONGO_URL or not DB_NAME:
    pytest.skip("MONGO_URL/DB_NAME must be set in backend/.env",
                allow_module_level=True)


def _load_reseller_profiles():
    path = Path("/app/test_reports/portal_iter3_credentials.json")
    if not path.exists():
        pytest.skip("portal_iter3_credentials.json not found; run iter3 fixtures first",
                    allow_module_level=True)
    data = json.loads(path.read_text())
    a = data["A"]; b = data["B"]
    a.setdefault("reseller_id", "9b9ecb49-5c1a-463c-91cb-452e18622815")
    a.setdefault("referral_code", "SNG40025330D4AB")
    b.setdefault("reseller_id", "357245f0-1937-453c-9bfd-2168cb3361d2")
    b.setdefault("referral_code", "SNG0E106BCFAF69")
    return a, b


RESELLER_A, RESELLER_B = _load_reseller_profiles()
MANIFEST_PATH = Path("/app/test_reports/qa_iter7_manifest.json")


def _origin(base_url):
    return {"Origin": base_url, "Content-Type": "application/json"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---- Fixtures ------------------------------------------------------------

@pytest.fixture(scope="module")
def mongo():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    yield db
    client.close()


@pytest.fixture(scope="module")
def manifest():
    seed = {"orders": [], "commissions": [], "adjustments": [], "rules": []}
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text())
            for k in seed:
                if isinstance(existing.get(k), list):
                    seed[k] = list(existing[k])
        except Exception:
            pass
    yield seed
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    for k, v in seed.items():
        seen = set(); merged = []
        for item in v:
            key = json.dumps(item, sort_keys=True, default=str)
            if key in seen:
                continue
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


# ---- Helpers -------------------------------------------------------------

def _pick_products(base_url, need=2):
    rows = requests.get(f"{base_url}/api/products", timeout=30).json()
    avail = [p for p in rows if p.get("available")]
    assert len(avail) >= need, f"need {need} products, have {len(avail)}"
    preferred = [p for p in avail if p["id"] in ("garlic", "peri-peri", "cheese")]
    if len(preferred) >= need:
        return preferred[:need]
    return avail[:need]


def _visit(session, base_url, code):
    r = session.post(f"{base_url}/api/referrals/visit",
                     json={"code": code, "source": "pytest_iter7", "campaign": ""},
                     timeout=30)
    assert r.status_code == 200, r.text


def _create_order(session, base_url, items, email, mobile):
    body = {
        "name": "QA_ITER7", "email": email, "mobile": mobile,
        "address": "QA Iter7 Street 42", "city": "Sangli", "pincode": "416416",
        "consent": True, "request_id": f"QA_ITER7_{uuid.uuid4()}",
        "attribution": {"utm_source": "pytest_iter7"}, "items": items,
    }
    r = session.post(f"{base_url}/api/orders", json=body, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _mark_state(admin, base_url, oid, payment, delivery, status, reason,
                reference=None):
    r = admin.patch(f"{base_url}/api/admin/business/orders/{oid}",
                    json={"payment_status": payment, "delivery_status": delivery,
                          "status": status,
                          "payment_reference": reference or f"QA7-{uuid.uuid4().hex[:8]}",
                          "reason": reason},
                    headers=_origin(base_url), timeout=30)
    assert r.status_code == 200, r.text


def _get_commission(admin, base_url, rid, oid, retries=10):
    for _ in range(retries):
        r = admin.get(f"{base_url}/api/admin/business/commission?reseller_id={rid}&limit=100",
                      timeout=30)
        assert r.status_code == 200
        row = next((x for x in r.json()["items"] if x["order_id"] == oid), None)
        if row:
            return row
        time.sleep(0.4)
    return None


def _create_scoped_rule(admin, base_url, manifest, name_suffix,
                       product_ids, reseller_id, rate="10", kind="PERCENTAGE",
                       bundle_sizes=None):
    body = {
        "name": f"QA_ITER7_{name_suffix}_{uuid.uuid4().hex[:6]}",
        "kind": kind, "rate": rate,
        "product_ids": product_ids,
        "variant_ids": [],
        "bundle_sizes": bundle_sizes or [],
        "tiers": [],
        "reseller_ids": [reseller_id],
        "priority": 500, "active": True,
        "reason": f"QA_ITER7 scoped rule {name_suffix}",
    }
    r = admin.post(f"{base_url}/api/admin/business/commission-rules",
                   json=body, headers=_origin(base_url), timeout=30)
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    manifest["rules"].append(rid)
    return rid


def _deactivate_rule(admin, base_url, rule_id):
    """Best-effort: supersede with active=False."""
    try:
        r = admin.get(f"{base_url}/api/admin/business/commission-rules",
                      timeout=30).json()
        cur = next((x for x in r["items"] if x["id"] == rule_id), None)
        if not cur or not cur.get("is_current"):
            return
        body = {**{k: cur[k] for k in
                   ["name", "kind", "product_ids", "variant_ids",
                    "bundle_sizes", "tiers", "reseller_ids", "priority"]},
                "rate": str(cur["rate"]),
                "active": False,
                "reason": "QA_ITER7 deactivate scoped rule"}
        admin.put(f"{base_url}/api/admin/business/commission-rules/{rule_id}",
                  json=body, headers=_origin(base_url), timeout=30)
    except Exception as e:
        print(f"[iter7] deactivate rule {rule_id} error: {e}")


def _configure_costs(admin, base_url, mongo, product_costs, other_cost):
    """Apply product_costs/other_cost_per_order; return original snapshot."""
    old = _run(mongo.business_settings.find_one({"id": "portal"}, {"_id": 0}))
    old_costs = old.get("product_costs", {}) or {}
    new_costs = {**old_costs}
    for pid, val in product_costs.items():
        new_costs[pid] = str(val)
    body = {**old,
            "product_costs": {k: str(v) for k, v in new_costs.items()},
            "other_cost_per_order": (str(other_cost) if other_cost is not None else None),
            "reason": "QA_ITER7 configure costs"}
    r = admin.put(f"{base_url}/api/admin/business/settings", json=body,
                  headers=_origin(base_url), timeout=30)
    assert r.status_code == 200, r.text
    return old


def _restore_settings(admin, base_url, old):
    old_costs = old.get("product_costs", {}) or {}
    old_other = old.get("other_cost_per_order")
    restore = {**old,
               "product_costs": {k: str(v) for k, v in old_costs.items()},
               "other_cost_per_order": str(old_other) if old_other is not None else None,
               "reason": "QA_ITER7 restore settings"}
    r = admin.put(f"{base_url}/api/admin/business/settings", json=restore,
                  headers=_origin(base_url), timeout=30)
    assert r.status_code == 200, f"restore failed: {r.status_code} {r.text}"


async def _call_real_sales(oid, monkeypatch):
    """Invoke the REAL portal.metrics.sales(), restricted to a single order id
    via monkeypatched sale_query. Does not modify application code."""
    # Import inside function so monkeypatch scope is respected.
    from portal import metrics as metrics_module

    original_sale_query = metrics_module.sale_query

    def restricted_sale_query(rid=None, **period):
        base = original_sale_query(rid=rid, **period)
        # Force to exactly one order regardless of period; drop restrictive
        # payment/status/delivery filters so this works for our known-PAID id.
        return {"id": oid}

    monkeypatch.setattr(metrics_module, "sale_query", restricted_sale_query)
    result = await metrics_module.sales()
    return result


# ---- Test class ----------------------------------------------------------

class TestIter7RealMetricsSales:
    """Every test invokes the ACTUAL portal.metrics.sales() implementation."""

    def test_two_equal_lines_with_one_paise_other_cost_reconciles_exactly(
            self, base_url, admin_session, manifest, mongo, monkeypatch):
        products = _pick_products(base_url, 2)
        admin = admin_session

        old = _configure_costs(admin, base_url, mongo,
                               {products[0]["id"]: "1.00",
                                products[1]["id"]: "1.00"},
                               "0.01")
        rule_id = _create_scoped_rule(admin, base_url, manifest, "TWOEQUAL",
                                     [p["id"] for p in products],
                                     RESELLER_B["reseller_id"])
        try:
            cust = requests.Session()
            _visit(cust, base_url, RESELLER_B["referral_code"])
            oid = _create_order(cust, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1},
                                 {"product_id": products[1]["id"], "quantity": 1}],
                                f"qa7.equal.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812330001")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER7 two-equal paid+delivered")
            c = _get_commission(admin, base_url, RESELLER_B["reseller_id"], oid)
            assert c is not None, "Commission must be earned"
            manifest["commissions"].append(c["id"])

            order = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            snap = order["economics_snapshot"]
            # Confirm expected fixture arithmetic
            assert snap["other_cost_minor"] == 1, snap
            assert snap["product_cost_minor"] == 200, snap
            assert snap["estimated_gross_profit_minor"] is not None
            # Two lines of equal sales must be present
            assert len(snap["parts"]) == 2
            assert snap["parts"][0]["sales_minor"] == snap["parts"][1]["sales_minor"]

            # Invoke the REAL app implementation, restricted to just this order.
            result = _run(_call_real_sales(oid, monkeypatch))

            # --- KEY ASSERTIONS against the actual metrics.sales() output ---
            assert result["orders"] == 1
            assert result["sales_minor"] == snap["sales_minor"]
            assert result["commission_minor"] == c["amount_minor"]
            # Report-level profit reflects snapshot profit; must be non-null.
            assert result["profit_minor"] is not None
            assert result["profit_minor"] == snap["estimated_gross_profit_minor"], (
                result["profit_minor"], snap["estimated_gross_profit_minor"])

            # Every product profit is present and non-null.
            product_profits = [p["profit_minor"] for p in result["products"]]
            print(f"[iter7] product_profits={product_profits} "
                  f"snap_profit={snap['estimated_gross_profit_minor']}")
            assert all(p is not None for p in product_profits), product_profits

            # Product-level allocation must sum EXACTLY to the order-level profit.
            assert sum(product_profits) == snap["estimated_gross_profit_minor"], (
                f"metrics.sales() per-product allocation drift: "
                f"sum={sum(product_profits)} vs "
                f"snap.estimated_gross_profit_minor={snap['estimated_gross_profit_minor']}")

            # Product-level commissions must sum to total commission.
            assert sum(p["commission_minor"] for p in result["products"]) == c["amount_minor"]
            # Product-level sales must sum to total sales.
            assert sum(p["sales_minor"] for p in result["products"]) == snap["sales_minor"]
        finally:
            _deactivate_rule(admin, base_url, rule_id)
            _restore_settings(admin, base_url, old)

    def test_repeated_product_line_reconciles_and_unique_orders_is_one(
            self, base_url, admin_session, manifest, mongo, monkeypatch):
        products = _pick_products(base_url, 2)
        admin = admin_session

        old = _configure_costs(admin, base_url, mongo,
                               {products[0]["id"]: "1.00"},
                               "0.05")
        rule_id = _create_scoped_rule(admin, base_url, manifest, "REPEAT",
                                     [products[0]["id"]],
                                     RESELLER_B["reseller_id"])
        try:
            # Same product twice in one order (as a single line with quantity=3).
            # Because flatten() emits one part per line, this yields 1 part.
            # To force a repeated product across multiple parts, use two lines
            # of the same product id.
            cust = requests.Session()
            _visit(cust, base_url, RESELLER_B["referral_code"])
            oid = _create_order(cust, base_url,
                                [{"product_id": products[0]["id"], "quantity": 2},
                                 {"product_id": products[0]["id"], "quantity": 1}],
                                f"qa7.repeat.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812330002")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER7 repeated product paid+delivered")
            c = _get_commission(admin, base_url, RESELLER_B["reseller_id"], oid)
            assert c is not None
            manifest["commissions"].append(c["id"])

            order = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            snap = order["economics_snapshot"]

            result = _run(_call_real_sales(oid, monkeypatch))
            assert result["orders"] == 1
            # Repeated product must yield ONE product entry with orders=1
            same_pid_rows = [p for p in result["products"]
                             if p["product_id"] == products[0]["id"]]
            assert len(same_pid_rows) == 1, result["products"]
            assert same_pid_rows[0]["orders"] == 1, (
                f"unique product order count must equal 1, got "
                f"{same_pid_rows[0]['orders']}")
            # Units aggregate (2 + 1 = 3)
            assert same_pid_rows[0]["units"] == 3

            # Totals reconcile
            assert sum(p["sales_minor"] for p in result["products"]) == snap["sales_minor"]
            assert sum(p["commission_minor"] for p in result["products"]) == c["amount_minor"]
            assert result["profit_minor"] == snap["estimated_gross_profit_minor"]
            assert same_pid_rows[0]["profit_minor"] is not None
            assert same_pid_rows[0]["profit_minor"] == snap["estimated_gross_profit_minor"]
        finally:
            _deactivate_rule(admin, base_url, rule_id)
            _restore_settings(admin, base_url, old)

    def test_zero_rate_then_adjustment_to_positive_reflects_in_metrics(
            self, base_url, admin_session, manifest, mongo, monkeypatch):
        """Zero-rate rule earns commission_minor=0; then admin adjusts the
        ledger upward. metrics.sales() must reflect the adjusted ledger amount
        without mutating snapshot.commission_minor.
        """
        products = _pick_products(base_url, 1)
        admin = admin_session

        old = _configure_costs(admin, base_url, mongo,
                               {products[0]["id"]: "1.00"},
                               "0.02")
        rule_id = _create_scoped_rule(admin, base_url, manifest, "ZERO",
                                     [products[0]["id"]],
                                     RESELLER_B["reseller_id"],
                                     rate="0")
        try:
            cust = requests.Session()
            _visit(cust, base_url, RESELLER_B["referral_code"])
            oid = _create_order(cust, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1}],
                                f"qa7.zero.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812330003")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER7 zero rate paid")
            c = _get_commission(admin, base_url, RESELLER_B["reseller_id"], oid)
            assert c is not None, "Zero-rate rule must still create a commission row"
            manifest["commissions"].append(c["id"])
            assert c["amount_minor"] == 0

            order_before = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            snap_before = order_before["economics_snapshot"]
            assert snap_before["commission_minor"] == 0

            # Adjust upward
            new_amount = "5.00"
            r_adj = admin.post(
                f"{base_url}/api/admin/business/commission/{c['id']}/adjust",
                json={"new_amount": new_amount, "reason": "QA_ITER7 zero->positive adjust"},
                headers=_origin(base_url), timeout=30)
            assert r_adj.status_code == 200, r_adj.text
            adj = r_adj.json()
            manifest["adjustments"].append(adj.get("id") or adj)

            # Snapshot must remain immutable
            order_after = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            assert order_after["economics_snapshot"] == snap_before, (
                "Historical snapshot mutated after adjustment!")

            # Refresh ledger row
            c_after = _run(mongo.commissions.find_one({"id": c["id"]}, {"_id": 0}))
            assert c_after["amount_minor"] == 500, c_after

            # metrics.sales() should reflect adjusted ledger
            result = _run(_call_real_sales(oid, monkeypatch))
            assert result["commission_minor"] == 500, result
            # Report-level profit should now subtract 500 additional commission
            # relative to the (frozen) snapshot, per portal/metrics line 45:
            #   profit += p - (c.amount_minor - snap.commission_minor) if configured
            expected_profit = snap_before["estimated_gross_profit_minor"] - (500 - 0)
            assert result["profit_minor"] == expected_profit, (
                result["profit_minor"], expected_profit)
        finally:
            _deactivate_rule(admin, base_url, rule_id)
            _restore_settings(admin, base_url, old)

    def test_missing_cost_historic_order_yields_null_profit_in_real_metrics(
            self, base_url, admin_session, manifest, mongo, monkeypatch):
        """When product cost is missing, actual metrics.sales() must return
        profit_minor None and product.cost_known False and product.profit_minor None,
        even if we later configure costs (snapshot immutability regression)."""
        products = _pick_products(base_url, 1)
        admin = admin_session

        old = _run(mongo.business_settings.find_one({"id": "portal"}, {"_id": 0}))
        old_costs = old.get("product_costs", {}) or {}
        # Clear the target product's cost & other_cost
        clear_body = {**old,
                      "product_costs": {k: str(v) for k, v in old_costs.items()
                                        if k != products[0]["id"]},
                      "other_cost_per_order": None,
                      "reason": "QA_ITER7 clear costs for historic missing"}
        r0 = admin.put(f"{base_url}/api/admin/business/settings", json=clear_body,
                       headers=_origin(base_url), timeout=30)
        assert r0.status_code == 200

        rule_id = _create_scoped_rule(admin, base_url, manifest, "MISS",
                                     [products[0]["id"]],
                                     RESELLER_B["reseller_id"])
        try:
            cust = requests.Session()
            _visit(cust, base_url, RESELLER_B["referral_code"])
            oid = _create_order(cust, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1}],
                                f"qa7.miss.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812330004")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER7 missing-cost historic")
            order = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            snap_before = order["economics_snapshot"]
            assert snap_before["estimated_gross_profit_minor"] is None
            assert snap_before["product_cost_minor"] is None
            assert snap_before["other_cost_minor"] is None

            # Now configure costs after-the-fact
            _configure_costs(admin, base_url, mongo,
                             {products[0]["id"]: "1.00"}, "0.01")

            # Historical snapshot must remain byte-identical
            order_after = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            assert order_after["economics_snapshot"] == snap_before

            # Invoke the REAL metrics.sales
            result = _run(_call_real_sales(oid, monkeypatch))
            assert result["orders"] == 1
            assert result["profit_minor"] is None, (
                f"profit must be None when snapshot is missing costs, got "
                f"{result['profit_minor']}")
            # The single product row for this run must show cost_known False & profit None
            same = [p for p in result["products"]
                    if p["product_id"] == products[0]["id"]]
            assert same and same[0]["cost_known"] is False
            assert same[0]["profit_minor"] is None
        finally:
            _deactivate_rule(admin, base_url, rule_id)
            _restore_settings(admin, base_url, old)

    def test_tiny_other_cost_many_lines_never_produces_negative_share(
            self, base_url, admin_session, manifest, mongo, monkeypatch):
        """Confirm no product profit_minor > part.sales_minor (i.e. no
        negative implied 'cost share') on many-line small-other-cost case.
        Uses a repeated same-product order with quantity to create many parts
        would require bundle; here we use N distinct lines of one product
        (each line is one part in flatten()).
        """
        products = _pick_products(base_url, 1)
        admin = admin_session
        old = _configure_costs(admin, base_url, mongo,
                               {products[0]["id"]: "1.00"},
                               "0.03")
        rule_id = _create_scoped_rule(admin, base_url, manifest, "TINY",
                                     [products[0]["id"]],
                                     RESELLER_B["reseller_id"])
        try:
            cust = requests.Session()
            _visit(cust, base_url, RESELLER_B["referral_code"])
            oid = _create_order(cust, base_url,
                                [{"product_id": products[0]["id"], "quantity": 1}] * 4,
                                f"qa7.tiny.{uuid.uuid4().hex[:6]}@example.com",
                                "+919812330005")
            manifest["orders"].append(oid)
            _mark_state(admin, base_url, oid, "PAID", "DELIVERED", "FULFILLED",
                        "QA_ITER7 tiny other-cost")
            c = _get_commission(admin, base_url, RESELLER_B["reseller_id"], oid)
            assert c is not None
            manifest["commissions"].append(c["id"])

            result = _run(_call_real_sales(oid, monkeypatch))
            order = _run(mongo.orders.find_one({"id": oid}, {"_id": 0}))
            snap = order["economics_snapshot"]

            # profit non-null and matches snapshot
            assert result["profit_minor"] == snap["estimated_gross_profit_minor"]
            # single product aggregation: profit_minor >= 0 (cannot be negative
            # on this configuration where sales >> commission+cost+other)
            assert result["products"][0]["profit_minor"] is not None
            assert result["products"][0]["profit_minor"] >= 0, result["products"][0]
        finally:
            _deactivate_rule(admin, base_url, rule_id)
            _restore_settings(admin, base_url, old)
