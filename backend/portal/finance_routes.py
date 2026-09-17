from fastapi import APIRouter,Depends,HTTPException,Query
from db import db,uid,now
from .security import permit
from .models import Rule,Reason,Adjustment,PayoutCreate,PayoutUpdate,Input
from .audit import audit,change
from .metrics import paginate,commission_totals
from .financial import create_payout,update_payout,adjust_commission,set_commission_state
from .settings import settings
from typing import Literal

router=APIRouter(prefix='/api/admin/business')

@router.get('/commission-rules')
async def rules(user=Depends(permit('finance'))):return {'items':await db.commission_rules.find({},{'_id':0}).sort('created_at',-1).limit(2000).to_list(2000)}

@router.post('/commission-rules')
@router.put('/commission-rules/{rule_id}')
async def save_rule(body:Rule,rule_id:str|None=None,user=Depends(permit('finance'))):
    if body.kind=='PERCENTAGE' and body.rate>100:raise HTTPException(422,'Percentage commission cannot exceed 100')
    if body.starts_at and body.ends_at and body.starts_at>=body.ends_at:raise HTTPException(422,'Promotion end must follow its start')
    for pid in body.product_ids+body.variant_ids:
        if not await db.products.find_one({'id':pid},{'_id':0,'id':1}):raise HTTPException(422,'Commission rules must reference real products/variants')
    site=await db.content.find_one({'id':'site'},{'_id':0,'bundles':1});config=await settings()
    if any(size not in [b['size'] for b in site['bundles']] for size in body.bundle_sizes):raise HTTPException(422,'Unknown bundle size')
    if any(t not in config['tiers'] for t in body.tiers):raise HTTPException(422,'Unknown reseller tier')
    for rid in body.reseller_ids:
        if not await db.resellers.find_one({'id':rid},{'_id':0,'id':1}):raise HTTPException(422,'Unknown reseller')
    old=await db.commission_rules.find_one({'id':rule_id},{'_id':0}) if rule_id else None
    if rule_id and not old:raise HTTPException(404,'Rule not found')
    if old and not old.get('is_current',True):raise HTTPException(409,'Edit the current version of this rule')
    doc={'id':uid(),'group_id':old['group_id'] if old else uid(),'version':old['version']+1 if old else 1,**body.model_dump(mode='json',exclude={'reason'}),'is_current':True,'created_at':now(),'updated_at':now()}
    if old:await change('commission_rules',{'id':rule_id,'is_current':True},{'active':False,'is_current':False},user,'COMMISSION_RULE_SUPERSEDED',body.reason)
    await db.commission_rules.insert_one(doc.copy());await audit(user,'COMMISSION_RULE_VERSION_CREATED','commission_rules',doc['id'],old,doc,body.reason)
    return doc

@router.get('/commission')
async def commissions(page:int=Query(1,ge=1),limit:int=Query(30,ge=1,le=100),reseller_id:str='',status:str='',user=Depends(permit('finance'))):
    q={}
    if reseller_id:q['reseller_id']=reseller_id
    if status:q['status']=status
    result=await paginate('commissions',q,page,limit);result['summary']=await commission_totals(reseller_id or None)
    result['adjustments']=await db.commission_adjustments.find({'reseller_id':reseller_id} if reseller_id else {},{'_id':0}).sort('created_at',-1).limit(100).to_list(100)
    return result

class CommissionState(Reason):status:Literal['APPROVED','PAYABLE']
@router.patch('/commission/{cid}/status')
async def commission_state(cid:str,body:CommissionState,user=Depends(permit('finance'))):return await set_commission_state(cid,body.status,user,body.reason)

@router.post('/commission/{cid}/adjust')
async def adjust(cid:str,body:Adjustment,user=Depends(permit('finance'))):return await adjust_commission(cid,body.new_amount,user,body.reason)

@router.get('/payouts')
async def payout_list(page:int=Query(1,ge=1),limit:int=Query(30,ge=1,le=100),reseller_id:str='',status:str='',user=Depends(permit('finance'))):
    q={}
    if reseller_id:q['reseller_id']=reseller_id
    if status:q['status']=status
    result=await paginate('payouts',q,page,limit);result['summary']=await commission_totals(reseller_id or None);return result

@router.post('/payouts')
async def payout_create(body:PayoutCreate,user=Depends(permit('finance'))):return await create_payout(body,user)

@router.patch('/payouts/{pid}')
async def payout_update(pid:str,body:PayoutUpdate,user=Depends(permit('finance'))):return await update_payout(pid,body,user)