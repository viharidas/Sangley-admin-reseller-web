import os,secrets,hashlib,hmac
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Request,Response,HTTPException
from pydantic import Field
from db import db,uid,now
from .settings import settings
from .security import digest,throttle,applicant
from .models import Input,phone
from .economics import snapshot

router=APIRouter(prefix='/api/referrals')
def customer_key(email):return hmac.new(os.environ['JWT_SECRET'].encode(),email.lower().strip().encode(),hashlib.sha256).hexdigest()

async def current_referral(request):
    value=request.cookies.get('sangley_referral')
    if not value:return None
    row=await db.referral_sessions.find_one({'token_hash':digest(value),'expires_at':{'$gt':datetime.now(timezone.utc)}},{'_id':0})
    if not row:return None
    profile=await db.resellers.find_one({'id':row['reseller_id'],'status':'APPROVED'},{'_id':0})
    return {'session':row,'profile':profile} if profile else None

class Visit(Input):
    code:str=Field(min_length=3,max_length=80)
    source:str=Field(default='referral_link',max_length=200)
    campaign:str=Field(default='',max_length=200)

@router.post('/visit')
async def visit(body:Visit,request:Request,response:Response):
    await throttle('referral:'+request.client.host,200,10)
    reseller=await db.resellers.find_one({'referral_code':body.code,'status':'APPROVED'},{'_id':0})
    if not reseller:raise HTTPException(404,'This reseller link is not active. You can still shop SANGLEY directly.')
    config=await settings();policy=config['campaign_policies'].get(body.campaign,config['referral_policy']);existing=await current_referral(request)
    visitor=request.cookies.get('sangley_visitor') or secrets.token_urlsafe(32)
    response.set_cookie('sangley_visitor',visitor,httponly=True,secure=True,samesite='none',max_age=31536000,path='/')
    if existing and policy in ('FIRST','OWNERSHIP'):
        selected=existing['profile'];sid=existing['session']['id']
    else:
        token=secrets.token_urlsafe(48);sid=uid();selected=reseller
        await db.referral_sessions.insert_one({'id':sid,'token_hash':digest(token),'reseller_id':reseller['id'],'referral_code':body.code,'source':body.source,'campaign':body.campaign,'policy':policy,'visitor_hash':digest(visitor),'created_at':now(),'expires_at':datetime.now(timezone.utc)+timedelta(days=config['attribution_days'])})
        response.set_cookie('sangley_referral',token,httponly=True,secure=True,samesite='none',max_age=config['attribution_days']*86400,path='/')
    await db.referral_events.insert_one({'id':uid(),'reseller_id':reseller['id'],'visitor_hash':digest(visitor),'name':'link_click','session_id':sid,'created_at':now()})
    return {'valid':True,'reseller_number':selected['reseller_number'],'destination':'/shop','attribution_preserved':selected['id']!=reseller['id']}

async def order_context(request,body,priced):
    key=customer_key(str(body.email));base={'customer_key':key,'source_system':'SANGLEY','external_order_id':None,'delivery_status':'NOT_SHIPPED','reseller_id':None,'order_channel':'D2C','updated_at':now()}
    ref=await current_referral(request);config=await settings()
    if request.cookies.get('reseller_access'):
        try:
            signed_in=await applicant(request)
        except HTTPException as exc:
            if exc.status_code!=401:raise
            signed_in=None
        if signed_in:
            buyer=signed_in['profile']
            try:buyer_mobile=phone(body.mobile)
            except ValueError:raise HTTPException(422,'Enter a valid mobile number with country code')
            if str(body.email).lower()==buyer['email'].lower() or buyer_mobile==buyer['mobile']:
                base.update({'order_channel':'RESELLER_SELF','self_reseller_id':buyer['id'],'attribution_exclusion':'SELF_REFERRAL'})
                ref=None
    if ref:
        profile=ref['profile']
        try:normalized=phone(body.mobile)
        except ValueError:raise HTTPException(422,'Enter a valid mobile number with country code')
        if str(body.email).lower()==profile['email'].lower() or normalized==profile['mobile'] or normalized==profile.get('whatsapp'):
            base.update({'order_channel':'RESELLER_SELF','attribution_exclusion':'SELF_REFERRAL'})
        else:
            previous=await db.orders.find_one({'customer_key':key,'payment_status':'PAID','status':{'$ne':'CANCELLED'}},{'_id':0,'id':1})
            if previous and not config['repeat_attribution']:base['attribution_exclusion']='REPEAT_ORDER_DISABLED'
            else:
                if ref['session']['policy']=='OWNERSHIP':
                    owner=await db.customer_ownership.find_one({'customer_key':key},{'_id':0})
                    if owner:
                        owned=await db.resellers.find_one({'id':owner['reseller_id'],'status':'APPROVED'},{'_id':0})
                        if owned:profile=owned
                base.update({'reseller_id':profile['id'],'referral_code':profile['referral_code'],'referral_source':ref['session']['source'],'attributed_at':ref['session']['created_at'],'referral_session_id':ref['session']['id'],'referral_visitor_hash':ref['session']['visitor_hash'],'order_channel':'REFERRAL','repeat_attribution_snapshot':config['repeat_attribution'],'attribution_policy':ref['session']['policy']})
    base['economics_snapshot']=await snapshot(priced['items'],profile if base['reseller_id'] else None)
    return base

async def track_referral_event(request,name,properties):
    mapping={'product_view':'product_view','add_to_cart':'add_to_cart','checkout':'checkout_started'}
    if name not in mapping:return
    ref=await current_referral(request)
    if not ref:return
    await db.referral_events.insert_one({'id':uid(),'reseller_id':ref['profile']['id'],'visitor_hash':ref['session']['visitor_hash'],'session_id':ref['session']['id'],'name':mapping[name],'product_id':properties.get('product_id'),'created_at':now()})