from fastapi import APIRouter,Depends,Query,HTTPException
from db import db,now,uid
from .security import reseller,public_profile,encrypt,decrypt
from .models import ProfileUpdate,Ticket,TicketUpdate
from .metrics import sales,commission_totals,referral_performance,paginate,order_summary,commissions_for,period_query
from .audit import change,audit
from .settings import settings
from .economics import minor
from datetime import datetime,timezone

router=APIRouter(prefix='/api/reseller')

@router.get('/dashboard')
async def dashboard(auth=Depends(reseller)):
    rid=auth['profile']['id'];month=datetime.now(timezone.utc).strftime('%Y-%m-01')
    return {'profile':public_profile(auth['profile']),'today':await sales(rid,days=1),'month':await sales(rid,start=month),'lifetime':await sales(rid),'commission':await commission_totals(rid),'unread_notifications':await db.portal_notifications.count_documents({'reseller_id':rid,'read':False})}

@router.get('/sales')
@router.get('/products/performance')
@router.get('/customers')
@router.get('/profit')
async def report(days:int|None=Query(None,ge=1,le=3660),start:str|None=None,end:str|None=None,auth=Depends(reseller)):
    return await sales(auth['profile']['id'],days=days,start=start,end=end)

@router.get('/orders')
async def orders(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),status:str|None=None,days:int|None=Query(None,ge=1,le=3660),start:str|None=None,end:str|None=None,auth=Depends(reseller)):
    query={'reseller_id':auth['profile']['id'],**period_query(days,start,end)}
    if status:query['status']=status
    result=await paginate('orders',query,page,limit);ledger=await commissions_for(result['items'])
    result['items']=[order_summary(o,ledger.get(o['id'])) for o in result['items']];return result

@router.get('/orders/{oid}')
async def order(oid:str,auth=Depends(reseller)):
    row=await db.orders.find_one({'id':oid,'reseller_id':auth['profile']['id']},{'_id':0})
    if not row:raise HTTPException(404,'Order not found')
    c=await db.commissions.find_one({'order_id':oid},{'_id':0});return order_summary(row,c)

@router.get('/commission')
async def commissions(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),auth=Depends(reseller)):
    rid=auth['profile']['id'];result=await paginate('commissions',{'reseller_id':rid},page,limit)
    result['summary']=await commission_totals(rid)
    result['adjustments']=await db.commission_adjustments.find({'reseller_id':rid},{'_id':0}).sort('created_at',-1).limit(100).to_list(100)
    return result

@router.get('/payouts')
async def payouts(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),auth=Depends(reseller)):
    rid=auth['profile']['id'];result=await paginate('payouts',{'reseller_id':rid},page,limit);result['summary']=await commission_totals(rid);return result

@router.get('/my-link')
async def my_link(auth=Depends(reseller)):
    return {'profile':public_profile(auth['profile']),'performance':await referral_performance(auth['profile']['id'])}

@router.get('/targets')
async def targets(auth=Depends(reseller)):
    rid=auth['profile']['id'];rows=await db.reseller_targets.find({'reseller_id':rid},{'_id':0}).sort('month',-1).limit(24).to_list(24)
    for row in rows:
        year,month=map(int,row['month'].split('-'));first=datetime(year,month,1,tzinfo=timezone.utc);nxt=datetime(year+1,1,1,tzinfo=timezone.utc) if month==12 else datetime(year,month+1,1,tzinfo=timezone.utc)
        from datetime import timedelta
        row['achievement']=await sales(rid,start=first.isoformat(),end=(nxt-timedelta(days=1)).isoformat())
    return {'items':rows}

@router.get('/marketing-toolkit')
async def marketing(auth=Depends(reseller)):
    return {'items':await db.marketing_assets.find({'active':True},{'_id':0}).sort('created_at',-1).limit(200).to_list(200)}

@router.get('/notifications')
async def notifications(page:int=Query(1,ge=1),limit:int=Query(20,ge=1,le=100),auth=Depends(reseller)):
    return await paginate('portal_notifications',{'reseller_id':auth['profile']['id']},page,limit)

@router.post('/notifications/read-all')
async def mark_all(auth=Depends(reseller)):
    result=await db.portal_notifications.update_many({'reseller_id':auth['profile']['id'],'read':False},{'$set':{'read':True,'read_at':now()}});return {'updated':result.modified_count}

@router.post('/notifications/{nid}/read')
async def mark_read(nid:str,auth=Depends(reseller)):
    result=await db.portal_notifications.update_one({'id':nid,'reseller_id':auth['profile']['id']},{'$set':{'read':True,'read_at':now()}})
    if not result.matched_count:raise HTTPException(404,'Notification not found')
    return {'ok':True}

@router.get('/profile')
async def profile(auth=Depends(reseller)):return public_profile(auth['profile'])

@router.patch('/profile')
async def update_profile(body:ProfileUpdate,auth=Depends(reseller)):
    data=body.model_dump(exclude_unset=True);private=decrypt(auth['profile'].get('private_details'))
    for field in ['pan','gst','account_name','account_number','ifsc']:
        if field in data:private[field]=data.pop(field) or ''
    if data.get('photo_file_id') and not await db.portal_files.find_one({'id':data['photo_file_id'],'owner_id':auth['user']['id'],'purpose':'avatar','is_deleted':False},{'_id':0,'id':1}):raise HTTPException(400,'Choose an avatar uploaded by your account')
    data['private_details']=encrypt(private)
    updated=await change('resellers',{'id':auth['profile']['id']},data,auth['user'],'RESELLER_PROFILE_UPDATED','Reseller updated permitted profile fields')
    return public_profile(updated)

@router.get('/support')
async def tickets(auth=Depends(reseller)):
    config=await settings();site=await db.content.find_one({'id':'site'},{'_id':0,'faqs':1})
    return {'items':await db.support_tickets.find({'reseller_id':auth['profile']['id']},{'_id':0}).sort('created_at',-1).limit(100).to_list(100),'contact':{k:config[k] for k in ['support_email','support_phone','support_whatsapp']},'faqs':site['faqs']}

@router.post('/support')
async def create_ticket(body:Ticket,auth=Depends(reseller)):
    for fid in body.attachment_ids:
        if not await db.portal_files.find_one({'id':fid,'owner_id':auth['user']['id'],'purpose':'support','is_deleted':False},{'_id':0,'id':1}):raise HTTPException(400,'Attachment does not belong to this account')
    doc={'id':'TKT-'+uid()[:8].upper(),'reseller_id':auth['profile']['id'],**body.model_dump(),'status':'OPEN','replies':[],'created_at':now(),'updated_at':now()}
    await db.support_tickets.insert_one(doc.copy());return doc

@router.post('/support/{tid}/reply')
async def ticket_reply(tid:str,body:TicketUpdate,auth=Depends(reseller)):
    old=await db.support_tickets.find_one({'id':tid,'reseller_id':auth['profile']['id']},{'_id':0})
    if not old:raise HTTPException(404,'Ticket not found')
    if body.status and body.status not in ['OPEN','CLOSED']:raise HTTPException(403,'Only support can set that status')
    if not body.message and not body.status:raise HTTPException(400,'Add a reply or a status change')
    replies=old['replies']+[{'id':uid(),'message':body.message,'author':'Reseller','created_at':now()}] if body.message else old['replies']
    return await change('support_tickets',{'id':tid,'reseller_id':auth['profile']['id']},{'replies':replies,'status':body.status or old['status']},auth['user'],'SUPPORT_REPLY','Reseller updated support ticket')