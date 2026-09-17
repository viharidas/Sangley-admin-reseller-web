"""Archive only QA_ITER4/5/6/7 reliability fixtures. Dry run unless --apply is supplied.

Historical audit logs and all unrelated records are retained. Uploaded objects are
not destroyed: flagged QA file metadata is soft-deleted to revoke app access.
"""
import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from pymongo import MongoClient
from bson.json_util import dumps
import os

load_dotenv(Path(__file__).resolve().parents[1] / '.env')
QA = re.compile(r'^QA[ _]ITER[4567](?:_| |$)', re.IGNORECASE)
SOURCE = re.compile(r'^pytest_iter[4567]$', re.IGNORECASE)


def plan_cleanup(db):
    rows = lambda collection, query: list(db[collection].find(query))
    ids = lambda docs: [doc['id'] for doc in docs]
    orders = rows('orders', {'request_id': QA})
    order_ids = ids(orders)
    commissions = rows('commissions', {'order_id': {'$in': order_ids}})
    commission_ids = ids(commissions)
    adjustments = rows('commission_adjustments', {'order_id': {'$in': order_ids}})
    adjustment_ids = ids(adjustments)
    payouts = rows('payouts', {'$or': [
        {'request_id': QA}, {'commission_ids': {'$in': commission_ids}},
        {'adjustment_ids': {'$in': adjustment_ids}}]})
    payout_ids = ids(payouts)
    for payout in payouts:
        if not QA.match(payout.get('request_id', '')):
            raise ValueError('An unlabelled payout references QA data; manual review required')
        if not set(payout['commission_ids']).issubset(commission_ids):
            raise ValueError('A QA payout includes unrelated commission; cleanup stopped')
        if not set(payout.get('adjustment_ids', [])).issubset(adjustment_ids):
            raise ValueError('A QA payout includes unrelated adjustments; cleanup stopped')
    for doc in commissions + adjustments:
        if doc.get('payout_id') and doc['payout_id'] not in payout_ids:
            raise ValueError('A QA ledger entry references an unrelated payout')

    rules = rows('commission_rules', {'name': QA})
    rule_ids = ids(rules)
    if db.orders.find_one({'id': {'$nin': order_ids},
                           'economics_snapshot.parts.rule_id': {'$in': rule_ids}}):
        raise ValueError('A QA rule is referenced by an unrelated historical order')
    ownership = rows('customer_ownership', {'first_paid_order_id': {'$in': order_ids}})
    if db.orders.find_one({'id': {'$nin': order_ids},
                           'customer_key': {'$in': [x['customer_key'] for x in ownership]}}):
        raise ValueError('QA customer ownership is shared with unrelated orders')

    session_ids = [o['referral_session_id'] for o in orders if o.get('referral_session_id')]
    sessions = rows('referral_sessions', {'$or': [
        {'id': {'$in': session_ids}}, {'source': SOURCE}]})
    session_ids = list(set(session_ids + ids(sessions)))
    if db.orders.find_one({'id': {'$nin': order_ids},
                           'referral_session_id': {'$in': session_ids}}):
        raise ValueError('QA referral session is shared with an unrelated order')
    events = rows('referral_events', {'session_id': {'$in': session_ids}})
    notifications = rows('portal_notifications', {
        'link': {'$in': ['/reseller/orders/' + oid for oid in order_ids]}})

    assets = rows('marketing_assets', {'title': QA})
    files = rows('portal_files', {'original_filename': QA, 'is_deleted': False})
    file_ids = ids(files)
    if db.marketing_assets.find_one({'id': {'$nin': ids(assets)}, 'file_id': {'$in': file_ids}}):
        raise ValueError('An unrelated marketing asset references a QA file')
    if db.support_tickets.find_one({'attachment_ids': {'$in': file_ids}}):
        raise ValueError('A support conversation references a QA file; retain it for review')
    if db.resellers.find_one({'photo_file_id': {'$in': file_ids}}):
        raise ValueError('A profile references a QA avatar; retain it for review')
    return {
        'payouts': payouts, 'commission_adjustments': adjustments,
        'commissions': commissions, 'customer_ownership': ownership,
        'orders': orders, 'commission_rules': rules,
        'referral_events': events, 'referral_sessions': sessions,
        'portal_notifications': notifications, 'marketing_assets': assets,
        'portal_files': files,
    }


def apply_cleanup(db, plan):
    stamp = datetime.now(timezone.utc).isoformat()
    archive = db.qa_reliability_archive
    # Preflight every original record before making changes.
    for collection, docs in plan.items():
        for doc in docs:
            if db[collection].find_one({'_id': doc['_id']}) != doc:
                raise ValueError('Fixture changed after preflight; run the dry run again')
    # Archive the complete batch durably BEFORE removing any business record.
    for collection, docs in plan.items():
        for doc in docs:
            archive.update_one({'_id': collection + ':' + doc['id']}, {'$setOnInsert': {
                'collection': collection, 'original': doc, 'archived_at': stamp,
                'reason': 'User-approved QA_ITER4/5/6/7 reliability fixture cleanup',
            }}, upsert=True)
    result = {}
    for collection, docs in plan.items():
        selected = [doc['_id'] for doc in docs]
        if collection == 'portal_files':
            count = db[collection].update_many({'_id': {'$in': selected}}, {'$set': {
                'is_deleted': True, 'qa_archived_at': stamp}}).modified_count
        else:
            count = db[collection].delete_many({'_id': {'$in': selected}}).deleted_count
        if count != len(docs):
            raise RuntimeError('Cleanup count mismatch; originals retained in qa_reliability_archive')
        result[collection] = count
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with MongoClient(os.environ['MONGO_URL']) as client:
        db = client[os.environ['DB_NAME']]
        plan = plan_cleanup(db)
        summary = {'mode': 'apply' if args.apply else 'dry-run',
                   'records': {k: [d['id'] for d in v] for k, v in plan.items()},
                   'counts': {k: len(v) for k, v in plan.items()},
                   'preserved': 'Unrelated records, authentication, original audit logs and stored objects'}
        if args.apply:
            summary['archived_and_removed'] = apply_cleanup(db, plan)
        print(dumps(summary, indent=2))


if __name__ == '__main__':
    main()
