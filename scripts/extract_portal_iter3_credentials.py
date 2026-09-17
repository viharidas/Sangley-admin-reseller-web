import json
import re
from pathlib import Path

from pymongo import MongoClient


def read_env(path: str):
    data = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def derive_password(email: str) -> str | None:
    m = re.match(r"qa_portal_([ab])_([a-f0-9]{8})@example\.com$", email)
    if not m:
        return None
    tag = m.group(1).upper()
    suffix = m.group(2)
    return f"QA_PORTAL_{tag}_{suffix}123"


def latest_by_tag(rows, tag: str):
    candidates = [r for r in rows if r["email"].startswith(f"qa_portal_{tag.lower()}_")]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return candidates[0]


def main():
    env = read_env("/app/backend/.env")
    mongo_url = env.get("MONGO_URL")
    db_name = env.get("DB_NAME")
    if not mongo_url or not db_name:
        raise SystemExit("Missing MONGO_URL or DB_NAME in backend/.env")

    db = MongoClient(mongo_url)[db_name]
    users = list(
        db.users.find(
            {"email": {"$regex": r"^qa_portal_[ab]_"}, "role": "reseller"},
            {"_id": 0, "id": 1, "email": 1, "created_at": 1},
        )
    )
    a = latest_by_tag(users, "A")
    b = latest_by_tag(users, "B")

    result = {
        "A": {
            "email": a["email"] if a else None,
            "password": derive_password(a["email"]) if a else None,
            "user_id": a["id"] if a else None,
        },
        "B": {
            "email": b["email"] if b else None,
            "password": derive_password(b["email"]) if b else None,
            "user_id": b["id"] if b else None,
        },
    }

    if a:
        reseller = db.resellers.find_one({"user_id": a["id"]}, {"_id": 0, "id": 1, "referral_code": 1, "reseller_number": 1})
        result["A"]["reseller_id"] = reseller.get("id") if reseller else None
        result["A"]["referral_code"] = reseller.get("referral_code") if reseller else None
        result["A"]["reseller_number"] = reseller.get("reseller_number") if reseller else None
        if reseller:
            order = db.orders.find_one(
                {"reseller_id": reseller["id"]},
                {"_id": 0, "id": 1, "payment_status": 1, "delivery_status": 1},
                sort=[("created_at", -1)],
            )
            if order:
                result["A"]["latest_order_id"] = order.get("id")
                result["A"]["latest_order_payment_status"] = order.get("payment_status")
                result["A"]["latest_order_delivery_status"] = order.get("delivery_status")
                commission = db.commissions.find_one({"order_id": order["id"]}, {"_id": 0, "id": 1, "status": 1, "amount_minor": 1})
                if commission:
                    result["A"]["latest_commission_id"] = commission.get("id")
                    result["A"]["latest_commission_status"] = commission.get("status")
                    result["A"]["latest_commission_amount_minor"] = commission.get("amount_minor")
                    payout = db.payouts.find_one(
                        {"commission_ids": commission["id"]},
                        {"_id": 0, "id": 1, "status": 1, "amount_minor": 1},
                        sort=[("created_at", -1)],
                    )
                    if payout:
                        result["A"]["latest_payout_id"] = payout.get("id")
                        result["A"]["latest_payout_status"] = payout.get("status")
                        result["A"]["latest_payout_amount_minor"] = payout.get("amount_minor")
    out = "/app/test_reports/portal_iter3_credentials.json"
    Path(out).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
