import re,secrets
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,Query,HTTPException
from pymongo import ReturnDocument
from db import db,uid,now
from .security import permit,public_profile
from .models import ResellerState,Reason,FinancialOrder,Target,Marketing,Announcement,TicketUpdate,ProfileUpdate
from .audit import audit,change,notify
from .settings import settings,BusinessSettings
from .metrics import sales,commission_totals,referral_performance,paginate,order_summary,commissions_for,period_query
from .economics import minor
from .financial import synchronize_order,ledger_lock

router=APIRouter(prefix='/api/admin/business')

class AdminProfileChange(ProfileUpdate):
    reason:str

@router.patch('/resellers/{rid}/profile')
async def edit_profile(rid:str,body:AdminProfileChange,user=Depends(permit('resellers'))):
    if len(body.reason.strip())<4:raise HTTPException(422,'A change reason is required')
    allowed={'full_name','city','address','community_type','network_size','whatsapp'}
    changes=body.model_dump(exclude_unset=True,exclude={'reason'})
    if set(changes)-allowed:raise HTTPException(403,'Use the verified owner workflow for bank, tax and identity changes')
    result=await change('resellers',{'id':rid},changes,user,'ADMIN_RESELLER_PROFILE_CHANGED',body.reason)
    if changes.get('full_name'):await db.users.update_one({'id':result['user_id']},{'$set':{'name':changes['full_name']}})
    return public_profile(result)

@router.get('/export')
async def export_business(user=Depends(permit('finance'))):
    data={'schema_version':'2.0','exported_at':now(),'source':'SANGLEY community system','currency':'INR','money_representation':'Integer paise in *_minor fields','integration_boundary':'Shopify commerce adapter -> immutable order snapshot -> SANGLEY referral, commission and payout services'}
    for collection in ['commission_rules','commissions','commission_adjustments','payouts','reseller_targets','marketing_assets','support_tickets','audit_logs','business_settings']:
        data[collection]=await db[collection].find({},{'_id':0}).to_list(100000)
    data['resellers']=[public_profile(r) for r in await db.resellers.find({},{'_id':0}).to_list(100000)]
    data['orders']=await db.orders.find({},{'_id':0}).to_list(100000)
    await audit(user,'BUSINESS_DATA_EXPORTED','exports',uid(),None,{'collections':list(data.keys())},'Authorised finance export; bank identifiers masked')
    return data

@router.get('/dashboard')
async def dashboard(days:int|None=Query(None,ge=1,le=3660),start:str|None=None,end:str|None=None,user=Depends(permit('resellers'))):
    overall=await sales(days=days,start=start,end=end)
    q={'payment_status':'PAID','status':{'$ne':'CANCELLED'},'delivery_status':{'$ne':'RETURNED'},**period_query(days,start,end)}
    channels=await db.orders.aggregate([{'$match':q},{'$group':{'_id':'$order_channel','sales':{'$sum':'$subtotal'},'orders':{'$sum':1}}}]).to_list(10)
    resellers=await db.resellers.find({},{'_id':0,'id':1,'status':1,'created_at':1}).to_list(100000)
    pipeline=await db.resellers.aggregate([{'$group':{'_id':'$status','count':{'$sum':1}}}]).to_list(10)
    return {'metrics':overall,'total_resellers':len(resellers),'active_resellers':sum(r['status']=='APPROVED' for r in resellers),'pending_applications':sum(r['status'] in ['PENDING','UNDER_REVIEW','HOLD'] for r in resellers),'new_resellers':await db.resellers.count_documents(period_query(days,start,end)),'commission':await commission_totals(),'pending_payouts':await db.payouts.count_documents({'status':{'$in':['PENDING','APPROVED']}}),'channels':[{'channel':c['_id'] or 'D2C','sales_minor':minor(c['sales']),'orders':c['orders']} for c in channels],'application_funnel':[{'status':r['_id'],'count':r['count']} for r in pipeline],'lead_count':await db.leads.count_documents({'type':'reseller'}),'rule_count':await db.commission_rules.count_documents({'active':True})}

@router.get('/resellers')
async def resellers(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),search:str='',status:str='',city:str='',start:str|None=None,end:str|None=None,user=Depends(permit('resellers'))):
    q=period_query(start=start,end=end)
    if status:q['status']=status
    if city:q['city']={'$regex':re.escape(city),'$options':'i'}
    if search:q['$or']=[{f:{'$regex':re.escape(search[:100]),'$options':'i'}} for f in ['full_name','email','mobile','reseller_number','city']]
    result=await paginate('resellers',q,page,limit)
    for i,row in enumerate(result['items']):
        m=await sales(row['id']);last=await db.orders.find_one({'reseller_id':row['id'],'payment_status':'PAID'},{'_id':0,'created_at':1},sort=[('created_at',-1)])
        result['items'][i]={**public_profile(row),'metrics':{k:m[k] for k in ['orders','units','sales_minor','commission_minor','profit_minor']},'last_order':last['created_at'] if last else None}
    return result

@router.get('/resellers/{rid}')
async def reseller_detail(rid:str,user=Depends(permit('resellers'))):
    row=await db.resellers.find_one({'id':rid},{'_id':0})
    if not row:raise HTTPException(404,'Reseller not found')
    return {'profile':public_profile(row),'sales':await sales(rid),'commission':await commission_totals(rid),'referral':await referral_performance(rid),'notes':await db.reseller_notes.find({'reseller_id':rid},{'_id':0}).sort('created_at',-1).limit(100).to_list(100),'targets':await db.reseller_targets.find({'reseller_id':rid},{'_id':0}).sort('month',-1).limit(24).to_list(24)}

@router.patch('/resellers/{rid}/status')
async def reseller_state(rid:str,body:ResellerState,user=Depends(permit('resellers'))):
    row=await db.resellers.find_one({'id':rid},{'_id':0})
    if not row:raise HTTPException(404,'Reseller not found')
    changes={'status':body.status,'status_reason':body.reason}
    config=await settings()
    if body.tier:
        if body.tier not in config['tiers']:raise HTTPException(400,'Choose a configured reseller tier')
        changes['tier']=body.tier
    if body.status=='APPROVED' and not row.get('reseller_number'):
        counter=await db.counters.find_one_and_update({'id':'reseller_sequence'},{'$inc':{'value':1}},upsert=True,return_document=ReturnDocument.AFTER,projection={'_id':0})
        changes.update({'reseller_number':f'SGR{counter["value"]:06d}','referral_code':'SNG'+secrets.token_hex(6).upper(),'approved_at':now(),'approved_by':user['id']})
    updated=await change('resellers',{'id':rid},changes,user,'RESELLER_'+body.status,body.reason)
    if body.status in ['SUSPENDED','INACTIVE','REJECTED']:
        await db.users.update_one({'id':row['user_id']},{'$inc':{'session_version':1}})
        await db.portal_sessions.update_many({'user_id':row['user_id']},{'$set':{'revoked':True}})
    await notify(rid,'ANNOUNCEMENT','Application status updated',f'Your SANGLEY application is now {body.status.lower().replace("_"," ")}.','/reseller/application-status')
    return public_profile(updated)

@router.post('/resellers/{rid}/notes')
async def add_note(rid:str,body:Reason,user=Depends(permit('resellers'))):
    if not await db.resellers.find_one({'id':rid},{'_id':0,'id':1}):raise HTTPException(404,'Reseller not found')
    row={'id':uid(),'reseller_id':rid,'note':body.reason,'author':user['name'],'created_at':now()};await db.reseller_notes.insert_one(row.copy());await audit(user,'RESELLER_NOTE_ADDED','resellers',rid,None,row,body.reason);return row

@router.get('/orders')
async def orders(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),reseller_id:str='',status:str='',channel:str='',start:str|None=None,end:str|None=None,user=Depends(permit('orders'))):
    q=period_query(start=start,end=end)
    if reseller_id:q['reseller_id']=reseller_id
    if status:q['status']=status
    if channel:q['order_channel']=channel
    result=await paginate('orders',q,page,limit);ledger=await commissions_for(result['items']);result['items']=[order_summary(o,ledger.get(o['id']),True) for o in result['items']];return result

@router.patch('/orders/{oid}')
async def update_order(oid:str,body:FinancialOrder,user=Depends(permit('orders'))):
    old=await db.orders.find_one({'id':oid},{'_id':0})
    if not old:raise HTTPException(404,'Order not found')
    if old.get('payment_status')=='PAID' and body.payment_status=='NOT_COLLECTED':raise HTTPException(409,'A recorded payment cannot be silently cleared. Record a refund instead.')
    if old.get('payment_status')=='REFUNDED' and body.payment_status!='REFUNDED':raise HTTPException(409,'Refund history cannot be rewritten; create a new order')
    if body.payment_status=='PAID' and not body.payment_reference.strip() and not old.get('payment_reference'):raise HTTPException(422,'Provide the actual payment reference before confirming payment')
    changes=body.model_dump(exclude={'reason'});changes['payment_reference']=body.payment_reference or old.get('payment_reference','')
    if old.get('payment_status')!=body.payment_status:
        config=await settings()
        if 'finance' not in config['roles_permissions'].get(user['role'],[]):raise HTTPException(403,'Finance permission is required to change payment state')
    async with ledger_lock(old.get('reseller_id'),skip=not bool(old.get('reseller_id'))):
        row=await change('orders',{'id':oid},changes,user,'ORDER_FINANCIAL_STATE_CHANGED',body.reason)
        await synchronize_order(row,user,lock_held=True)
    if row.get('reseller_id') and old.get('delivery_status')!=row['delivery_status'] and row['delivery_status'] in ['SHIPPED','DELIVERED']:await notify(row['reseller_id'],'ORDER_'+row['delivery_status'],'Order '+row['delivery_status'].lower(),f'Order {oid} has been updated.','/reseller/orders/'+oid)
    ledger=await db.commissions.find_one({'order_id':oid},{'_id':0});return order_summary(row,ledger,True)

@router.get('/sales')
async def sales_report(reseller_id:str='',days:int|None=Query(None,ge=1,le=3660),start:str|None=None,end:str|None=None,user=Depends(permit('finance'))):return await sales(reseller_id or None,days=days,start=start,end=end)

@router.get('/settings')
async def get_settings(user=Depends(permit('settings'))):return await settings()

@router.put('/settings')
async def save_settings(body:dict,user=Depends(permit('settings'))):
    reason=body.pop('reason','')
    if len(reason.strip())<4:raise HTTPException(422,'Explain the reason for this settings change')
    from pydantic import ValidationError
    try:config=BusinessSettings.model_validate({k:v for k,v in body.items() if k not in ['id','created_at','updated_at']})
    except ValidationError as exc:raise HTTPException(422,'; '.join(e['msg'] for e in exc.errors()))
    allowed_fields={'full_name','email','mobile','city','address','community_type','network_size','whatsapp','referral_source','pan','gst','account_name','account_number','ifsc','terms_accepted'}
    if any(k not in allowed_fields for k in config.required_fields):raise HTTPException(422,'Unsupported mandatory registration field')
    if not {'full_name','email','mobile','city','community_type','terms_accepted'}.issubset(set(config.required_fields)):raise HTTPException(422,'Core identity and consent fields must remain mandatory')
    if len(set(config.tiers))!=len(config.tiers) or not config.tiers:raise HTTPException(422,'Configure at least one uniquely named tier')
    for pid,cost in config.product_costs.items():
        if cost<0 or not cost.is_finite() or not await db.products.find_one({'id':pid},{'_id':0,'id':1}):raise HTTPException(422,'Product costs must reference existing products and nonnegative amounts')
    if not {'settings','audit'}.issubset(set(config.roles_permissions.get('admin',[]))):raise HTTPException(422,'Admin must retain settings and audit access')
    if config.notification_preferences.get('email') or config.notification_preferences.get('whatsapp'):raise HTTPException(422,'Connect your delivery providers before enabling outbound notifications')
    return await change('business_settings',{'id':'portal'},config.model_dump(mode='json'),user,'BUSINESS_SETTINGS_CHANGED',reason)

@router.get('/targets')
async def target_list(reseller_id:str='',user=Depends(permit('resellers'))):return {'items':await db.reseller_targets.find({'reseller_id':reseller_id} if reseller_id else {},{'_id':0}).sort('month',-1).limit(1000).to_list(1000)}

@router.post('/targets')
async def save_target(body:Target,user=Depends(permit('resellers'))):
    if not await db.resellers.find_one({'id':body.reseller_id},{'_id':0,'id':1}):raise HTTPException(404,'Reseller not found')
    values=body.model_dump(mode='json',exclude={'reason','sales_target','commission_target'});values['sales_target_minor']=minor(body.sales_target) if body.sales_target is not None else None;values['commission_target_minor']=minor(body.commission_target) if body.commission_target is not None else None
    old=await db.reseller_targets.find_one({'reseller_id':body.reseller_id,'month':body.month},{'_id':0})
    if old:row=await change('reseller_targets',{'id':old['id']},values,user,'TARGET_UPDATED',body.reason)
    else:
        row={'id':uid(),**values,'created_at':now(),'updated_at':now()};await db.reseller_targets.insert_one(row.copy());await audit(user,'TARGET_CREATED','reseller_targets',row['id'],None,row,body.reason)
    await notify(body.reseller_id,'TARGET_UPDATE','Your target has been updated','See your configured goals and actual progress.','/reseller/targets');return row

@router.get('/marketing')
async def marketing(user=Depends(permit('marketing'))):return {'items':await db.marketing_assets.find({},{'_id':0}).sort('created_at',-1).limit(1000).to_list(1000)}

@router.post('/marketing')
@router.put('/marketing/{mid}')
async def save_marketing(body:Marketing,mid:str|None=None,user=Depends(permit('marketing'))):
    if not body.file_id and not body.url:raise HTTPException(422,'Upload a real file or provide a real HTTPS resource link')
    if body.file_id and not await db.portal_files.find_one({'id':body.file_id,'purpose':'marketing','is_deleted':False},{'_id':0,'id':1}):raise HTTPException(400,'Marketing file not found')
    if mid:return await change('marketing_assets',{'id':mid},body.model_dump(),user,'MARKETING_ASSET_UPDATED','Business content updated')
    row={'id':uid(),**body.model_dump(),'created_at':now(),'updated_at':now()};await db.marketing_assets.insert_one(row.copy());await audit(user,'MARKETING_ASSET_CREATED','marketing_assets',row['id'],None,row,'Real resource published');return row

@router.get('/notifications')
async def announcements(user=Depends(permit('marketing'))):return {'items':await db.announcements.find({},{'_id':0}).sort('created_at',-1).limit(100).to_list(100)}

@router.post('/notifications')
async def announce(body:Announcement,user=Depends(permit('marketing'))):
    q={'id':body.reseller_id} if body.reseller_id else {'status':'APPROVED'}
    recipients=await db.resellers.find(q,{'_id':0,'id':1}).to_list(100000)
    if body.reseller_id and not recipients:raise HTTPException(404,'Reseller not found')
    row={'id':uid(),**body.model_dump(),'recipient_count':len(recipients),'created_at':now()};await db.announcements.insert_one(row.copy())
    for recipient in recipients:await notify(recipient['id'],body.type,body.title,body.message,'/reseller/notifications')
    await audit(user,'ANNOUNCEMENT_SENT','announcements',row['id'],None,row,'In-app notification');return row

@router.get('/support')
async def support(reseller_id:str='',user=Depends(permit('support'))):return {'items':await db.support_tickets.find({'reseller_id':reseller_id} if reseller_id else {},{'_id':0}).sort('created_at',-1).limit(1000).to_list(1000)}

@router.post('/support/{tid}/reply')
async def reply(tid:str,body:TicketUpdate,user=Depends(permit('support'))):
    old=await db.support_tickets.find_one({'id':tid},{'_id':0})
    if not old:raise HTTPException(404,'Ticket not found')
    replies=old['replies']+[{'id':uid(),'message':body.message,'author':'SANGLEY Support','created_at':now()}] if body.message else old['replies']
    row=await change('support_tickets',{'id':tid},{'status':body.status or old['status'],'replies':replies},user,'SUPPORT_UPDATED','Support response/status update')
    await notify(old['reseller_id'],'ANNOUNCEMENT','Support ticket updated',old['subject'],'/reseller/support');return row

@router.get('/audit-log')
async def audit_list(page:int=Query(1,ge=1),limit:int=Query(30,ge=1,le=100),entity_id:str='',action:str='',user=Depends(permit('audit'))):
    query={}
    if entity_id:query['$or']=[{'entity_id':entity_id},{'new_value.reseller_id':entity_id},{'old_value.reseller_id':entity_id}]
    if action:query['action']={'$regex':re.escape(action),'$options':'i'}
    return await paginate('audit_logs',query,page,limit)