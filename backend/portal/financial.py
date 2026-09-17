from contextlib import asynccontextmanager
from datetime import datetime,timezone,timedelta,date
from pymongo.errors import DuplicateKeyError
from pymongo import ReturnDocument
from fastapi import HTTPException
from db import db,now,uid
from .audit import audit,change,notify
from .economics import minor
from .settings import settings

@asynccontextmanager
async def ledger_lock(rid,skip=False):
    if skip:
        yield None
        return
    token=uid();stamp=datetime.now(timezone.utc)
    try:
        row=await db.financial_locks.find_one_and_update({'id':rid,'expires_at':{'$lt':stamp}},{'$set':{'token':token,'expires_at':stamp+timedelta(seconds=60)}},upsert=True,return_document=ReturnDocument.AFTER)
    except DuplicateKeyError:raise HTTPException(409,'Another financial action is in progress. Please retry shortly.')
    try:yield row
    finally:await db.financial_locks.delete_one({'id':rid,'token':token})

async def synchronize_order(order,actor,lock_held=False):
    rid=order.get('reseller_id')
    if not rid:return
    async with ledger_lock(rid,skip=lock_held):
        ledger=await db.commissions.find_one({'order_id':order['id']},{'_id':0})
        cancelled=order['status']=='CANCELLED' or order['payment_status']=='REFUNDED' or order.get('delivery_status')=='RETURNED'
        if cancelled:
            if not ledger:return
            if ledger.get('payout_id'):
                payout=await db.payouts.find_one({'id':ledger['payout_id']},{'_id':0})
                if payout and payout['status']=='PAID':
                    existing=await db.commission_adjustments.find_one({'commission_id':ledger['id'],'kind':'ORDER_REVERSAL'},{'_id':0,'id':1})
                    if not existing:
                        prior=await db.commission_adjustments.find({'commission_id':ledger['id'],'affects_payout':True},{'_id':0}).to_list(1000)
                        effective=ledger['amount_minor']+sum(a['difference_minor'] for a in prior)
                        adjustment={'id':uid(),'reseller_id':rid,'commission_id':ledger['id'],'order_id':order['id'],'old_amount_minor':effective,'new_amount_minor':0,'difference_minor':-effective,'reason':'Order cancelled, refunded or returned after payout','kind':'ORDER_REVERSAL','affects_payout':True,'payout_id':None,'created_at':now(),'actor_id':actor['id']}
                        aid=await audit(actor,'PAID_COMMISSION_REVERSAL','commission_adjustments',adjustment['id'],None,adjustment,adjustment['reason'],'PENDING')
                        await db.commission_adjustments.insert_one(adjustment.copy());await db.audit_logs.update_one({'id':aid},{'$set':{'outcome':'COMPLETED'}})
                    return
                if payout and payout['status'] in ['PENDING','APPROVED']:
                    await change('payouts',{'id':payout['id']},{'status':'FAILED','notes':'Reserved order cancelled/refunded/returned'},actor,'PAYOUT_INVALIDATED','A reserved order became ineligible')
                    await release_payout(payout['id'])
            if ledger['status']!='CANCELLED':await change('commissions',{'id':ledger['id']},{'status':'CANCELLED','payout_id':None},actor,'COMMISSION_CANCELLED','Order became ineligible')
            return
        if order['payment_status']!='PAID' or ledger:return
        try:await db.customer_ownership.update_one({'customer_key':order['customer_key']},{'$setOnInsert':{'id':uid(),'customer_key':order['customer_key'],'reseller_id':rid,'first_paid_order_id':order['id'],'created_at':now()}},upsert=True)
        except DuplicateKeyError:pass
        owner=await db.customer_ownership.find_one({'customer_key':order['customer_key']},{'_id':0})
        if not order.get('repeat_attribution_snapshot',False) and owner['first_paid_order_id']!=order['id']:
            await db.orders.update_one({'id':order['id']},{'$set':{'commission_exclusion':'REPEAT_ORDER_DISABLED'}});return
        snap=order.get('economics_snapshot')
        if not snap or not snap.get('configured'):return
        doc={'id':uid(),'order_id':order['id'],'reseller_id':rid,'amount_minor':snap['commission_minor'],'original_amount_minor':snap['commission_minor'],'rule_snapshot':snap['parts'],'status':'PENDING','payout_id':None,'created_at':now(),'updated_at':now()}
        aid=await audit(actor,'COMMISSION_CREATED','commissions',doc['id'],None,doc,'Confirmed payment; original order rule snapshot','PENDING')
        try:await db.commissions.insert_one(doc.copy())
        except DuplicateKeyError:return
        await db.audit_logs.update_one({'id':aid},{'$set':{'outcome':'COMPLETED'}})
        await notify(rid,'COMMISSION_EARNED','Commission recorded','A paid order has a pending commission. Eligibility approval is still required.','/reseller/commission')

async def set_commission_state(cid,target,actor,reason):
    row=await db.commissions.find_one({'id':cid},{'_id':0})
    if not row:raise HTTPException(404,'Commission not found')
    async with ledger_lock(row['reseller_id']):
        row=await db.commissions.find_one({'id':cid},{'_id':0})
        order=await db.orders.find_one({'id':row['order_id']},{'_id':0})
        if row.get('payout_id'):raise HTTPException(409,'Commission is reserved by a payout')
        allowed={'PENDING':['APPROVED'],'ADJUSTED':['APPROVED'],'APPROVED':['PAYABLE'],'PAYABLE':[]}
        if target not in allowed.get(row['status'],[]):raise HTTPException(409,'This commission status transition is not allowed')
        if order['payment_status']!='PAID' or order.get('delivery_status')!='DELIVERED' or order['status']=='CANCELLED':raise HTTPException(409,'Confirmed payment and delivery are required before eligibility approval')
        profile=await db.resellers.find_one({'id':row['reseller_id']},{'_id':0,'status':1})
        if not profile or profile['status']!='APPROVED':raise HTTPException(409,'The reseller must be active and approved')
        result=await change('commissions',{'id':cid,'status':row['status']},{'status':target,'approved_by':actor['id'],'approved_at':now()},actor,'COMMISSION_'+target,reason)
        await notify(row['reseller_id'],'COMMISSION_APPROVED','Commission '+target.lower(),'Your commission record has been updated.','/reseller/commission')
        return result

async def adjust_commission(cid,new_amount,actor,reason):
    row=await db.commissions.find_one({'id':cid},{'_id':0})
    if not row:raise HTTPException(404,'Commission not found')
    async with ledger_lock(row['reseller_id']):
        row=await db.commissions.find_one({'id':cid},{'_id':0});paid=row['status']=='PAID'
        if row.get('payout_id') and not paid:raise HTTPException(409,'Fail/release the reserved payout before adjusting commission')
        if row['status']=='CANCELLED':raise HTTPException(409,'Cancelled commission cannot be adjusted')
        prior=await db.commission_adjustments.find({'commission_id':cid,'affects_payout':True},{'_id':0}).to_list(1000)
        old=row['amount_minor']+sum(x['difference_minor'] for x in prior) if paid else row['amount_minor'];new=minor(new_amount)
        if new==old:raise HTTPException(400,'The new amount is unchanged')
        adjustment={'id':uid(),'commission_id':cid,'order_id':row['order_id'],'reseller_id':row['reseller_id'],'old_amount_minor':old,'new_amount_minor':new,'difference_minor':new-old,'reason':reason,'actor_id':actor['id'],'kind':'MANUAL','affects_payout':paid,'payout_id':None,'created_at':now()}
        if not paid:await change('commissions',{'id':cid,'status':row['status']},{'amount_minor':new,'status':'ADJUSTED'},actor,'COMMISSION_ADJUSTED',reason)
        aid=await audit(actor,'COMMISSION_ADJUSTMENT_RECORDED','commission_adjustments',adjustment['id'],{'amount_minor':old},{'amount_minor':new,'difference_minor':new-old,'reseller_id':row['reseller_id']},reason,'PENDING')
        await db.commission_adjustments.insert_one(adjustment.copy());await db.audit_logs.update_one({'id':aid},{'$set':{'outcome':'COMPLETED'}})
        return adjustment

async def release_payout(pid):
    await db.commissions.update_many({'payout_id':pid,'status':{'$ne':'PAID'}},{'$set':{'payout_id':None}})
    await db.commission_adjustments.update_many({'payout_id':pid},{'$set':{'payout_id':None}})

async def create_payout(body,actor):
    previous=await db.payouts.find_one({'request_id':body.request_id},{'_id':0})
    if previous:
        if previous['reseller_id']!=body.reseller_id or sorted(previous['commission_ids'])!=sorted(body.commission_ids):raise HTTPException(409,'This request ID already belongs to a different payout request')
        return previous
    rid=body.reseller_id;ids=list(set(body.commission_ids))
    if len(ids)!=len(body.commission_ids):raise HTTPException(400,'Duplicate commission entries are not allowed')
    async with ledger_lock(rid):
        reseller=await db.resellers.find_one({'id':rid,'status':'APPROVED'},{'_id':0,'id':1})
        if not reseller:raise HTTPException(409,'Reseller must be approved before preparing a payout')
        entries=await db.commissions.find({'id':{'$in':ids},'reseller_id':rid,'status':'PAYABLE','payout_id':None},{'_id':0}).to_list(101)
        if len(entries)!=len(ids):raise HTTPException(409,'Every selected commission must be payable, unreserved and belong to this reseller')
        for entry in entries:
            order=await db.orders.find_one({'id':entry['order_id']},{'_id':0,'status':1,'payment_status':1,'delivery_status':1})
            if not order or order['payment_status']!='PAID' or order['delivery_status']!='DELIVERED' or order['status']=='CANCELLED':raise HTTPException(409,'A selected order is no longer eligible')
        adjustments=await db.commission_adjustments.find({'reseller_id':rid,'affects_payout':True,'payout_id':None},{'_id':0}).to_list(10000)
        amount=sum(c['amount_minor'] for c in entries)+sum(a['difference_minor'] for a in adjustments)
        config=await settings()
        if amount<=0 or amount<minor(config['minimum_payout']):raise HTTPException(400,'Net payout must be positive and meet the configured minimum')
        doc={'id':'PAY-'+uid()[:10].upper(),'request_id':body.request_id,'reseller_id':rid,'commission_ids':ids,'adjustment_ids':[a['id'] for a in adjustments],'amount_minor':amount,'commission_total_minor':sum(c['amount_minor'] for c in entries),'adjustment_total_minor':sum(a['difference_minor'] for a in adjustments),'status':'PENDING','reservation_complete':False,'notes':body.reason,'payment_reference':'','payment_date':None,'created_at':now(),'updated_at':now()}
        aid=await audit(actor,'PAYOUT_RESERVATION_STARTED','payouts',doc['id'],None,doc,body.reason,'PENDING')
        await db.payouts.insert_one(doc.copy())
        claimed=await db.commissions.update_many({'id':{'$in':ids},'status':'PAYABLE','payout_id':None},{'$set':{'payout_id':doc['id']}})
        if claimed.modified_count!=len(ids):
            await release_payout(doc['id']);await db.payouts.update_one({'id':doc['id']},{'$set':{'status':'FAILED','notes':'Concurrent reservation conflict'}});raise HTTPException(409,'Reservation conflict. Refresh and try again.')
        await db.commission_adjustments.update_many({'id':{'$in':doc['adjustment_ids']},'payout_id':None},{'$set':{'payout_id':doc['id']}})
        await db.payouts.update_one({'id':doc['id']},{'$set':{'reservation_complete':True}});doc['reservation_complete']=True
        await db.audit_logs.update_one({'id':aid},{'$set':{'outcome':'COMPLETED'}})
        await audit(actor,'PAYOUT_PREPARED','payouts',doc['id'],None,doc,body.reason)
        return doc

async def update_payout(pid,body,actor):
    row=await db.payouts.find_one({'id':pid},{'_id':0})
    if not row:raise HTTPException(404,'Payout not found')
    async with ledger_lock(row['reseller_id']):
        row=await db.payouts.find_one({'id':pid},{'_id':0})
        allowed={'PENDING':['APPROVED','FAILED'],'APPROVED':['PAID','FAILED','ADJUSTED'],'ADJUSTED':['APPROVED','FAILED'],'PAID':[],'FAILED':[]}
        if body.status not in allowed.get(row['status'],[]):raise HTTPException(409,'This payout transition is not allowed; paid history is permanent')
        if not row.get('reservation_complete') and body.status!='FAILED':raise HTTPException(409,'Reservation is incomplete. Mark failed to release it and prepare a new payout.')
        updates={'status':body.status,'notes':body.notes or row['notes']}
        if body.status in ['APPROVED','PAID']:
            profile=await db.resellers.find_one({'id':row['reseller_id']},{'_id':0,'status':1})
            if not profile or profile['status']!='APPROVED':raise HTTPException(409,'The reseller is not currently approved')
            entries=await db.commissions.find({'id':{'$in':row['commission_ids']},'payout_id':pid,'status':'PAYABLE'},{'_id':0}).to_list(101)
            if len(entries)!=len(row['commission_ids']):raise HTTPException(409,'A reserved commission has changed. Review or fail this payout.')
            for entry in entries:
                order=await db.orders.find_one({'id':entry['order_id']},{'_id':0,'status':1,'payment_status':1,'delivery_status':1})
                if not order or order['payment_status']!='PAID' or order['delivery_status']!='DELIVERED' or order['status']=='CANCELLED':raise HTTPException(409,'A reserved order is no longer eligible. Do not pay this payout.')
        if body.status=='PAID':
            if not body.actual_payment_confirmed or len(body.payment_reference.strip())<3 or not body.payment_date or len(body.notes.strip())<4:raise HTTPException(422,'Confirm actual payment and provide a payment reference, payment date and notes')
            if body.payment_date>date.today():raise HTTPException(422,'Payment date cannot be in the future')
            updates.update({'payment_reference':body.payment_reference,'payment_date':body.payment_date.isoformat(),'paid_by':actor['id'],'paid_at':now()})
        result=await change('payouts',{'id':pid,'status':row['status']},updates,actor,'PAYOUT_'+body.status,body.reason)
        if body.status=='FAILED':await release_payout(pid)
        if body.status=='PAID':
            await db.commissions.update_many({'payout_id':pid},{'$set':{'status':'PAID','paid_at':now(),'updated_at':now()}})
            await notify(row['reseller_id'],'PAYOUT_PROCESSED','Payout recorded','Your payout has been marked paid with a payment reference.','/reseller/payouts')
        return result

async def reconcile_paid_payouts():
    async for payout in db.payouts.find({'status':'PAID'},{'_id':0,'id':1,'paid_at':1}):
        await db.commissions.update_many({'payout_id':payout['id'],'status':{'$ne':'PAID'}},{'$set':{'status':'PAID','paid_at':payout['paid_at']}})