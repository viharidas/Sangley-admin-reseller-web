import math
from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError
from db import db, now
from auth import admin
from models import Product, Record, StatusUpdate
from content_models import SiteContent
from pydantic import ValidationError

router=APIRouter(prefix='/api/admin',dependencies=[Depends(admin)])
LEAD_STATUSES=['NEW LEAD','CONTACTED','INTERESTED','ONBOARDING','ACTIVE','FIRST ORDER','REPEAT ORDER','INACTIVE']
ORDER_STATUSES=['ENQUIRY','CONTACTED','CONFIRMED','FULFILLED','CANCELLED']

@router.get('/overview')
async def overview():
    return {'products':await db.products.count_documents({}),'orders':await db.orders.count_documents({}),'reseller_leads':await db.leads.count_documents({'type':'reseller'}),'consumer_leads':await db.leads.count_documents({'type':{'$ne':'reseller'}}),'events':await db.events.count_documents({}),'new_leads':await db.leads.count_documents({'status':'NEW LEAD'})}

@router.put('/products/{pid}',response_model=Product)
async def save_product(pid:str,body:Product):
    if pid!=body.id: raise HTTPException(400,'Product ID cannot be changed')
    if not math.isfinite(body.price) or (body.mrp is not None and not math.isfinite(body.mrp)): raise HTTPException(400,'Price must be finite')
    try: await db.products.update_one({'id':pid},{'$set':body.model_dump()},upsert=True)
    except DuplicateKeyError: raise HTTPException(400,'That product URL is already in use')
    return body

@router.delete('/products/{pid}')
async def delete_product(pid:str):
    result=await db.products.delete_one({'id':pid})
    if not result.deleted_count: raise HTTPException(404,'Product not found')
    return {'ok':True}

@router.put('/content',response_model=Record)
async def save_content(body:dict):
    current=await db.content.find_one({'id':'site'},{'_id':0})
    for field in body:
        if field not in current: raise HTTPException(400,f'Unknown content field: {field}')
        if current[field] is not None and type(body[field]) is not type(current[field]): raise HTTPException(400,f'Invalid format for {field}')
    merged={**current,**body,'id':'site'}
    try:
        merged=SiteContent.model_validate(merged).model_dump()
    except ValidationError as exc:
        details='; '.join(f'{".".join(map(str,e["loc"]))}: {e["msg"]}' for e in exc.errors())
        raise HTTPException(422,details)
    try:
        if not all(k in merged['hero'] for k in ('line1','line2','eyebrow','description')): raise ValueError('Hero requires headline and description')
        if not isinstance(merged['faqs'],list) or any(not f.get('question') or not f.get('answer') for f in merged['faqs']): raise ValueError('Every FAQ needs a question and answer')
        sizes=[]
        for b in merged['bundles']:
            if b['size'] not in (4,6,8) or b['size'] in sizes: raise ValueError('Use unique box sizes of 4, 6 or 8')
            sizes.append(b['size'])
            if b.get('price') is not None and (not isinstance(b['price'],(float,int)) or b['price']<0 or not math.isfinite(b['price'])): raise ValueError('Box prices must be nonnegative numbers or null')
        for field in ['cost_per_pack','selling_price']:
            v=merged['reseller'].get(field)
            if v is not None and (not isinstance(v,(int,float)) or v<0 or not math.isfinite(v)): raise ValueError('Reseller prices must be nonnegative numbers or null')
        for kit in merged['reseller']['kits']:
            for key in ['price','quantity','margin']:
                v=kit.get(key)
                if v is not None and (not isinstance(v,(int,float)) or v<0 or not math.isfinite(v)): raise ValueError('Starter option values must be nonnegative numbers or null')
        phone=merged['whatsapp_number']
        if phone and (not phone.isdigit() or not 10<=len(phone)<=15): raise ValueError('WhatsApp requires 10–15 digits including country code, without +')
    except (KeyError,TypeError,ValueError) as e: raise HTTPException(400,str(e))
    await db.content.update_one({'id':'site'},{'$set':merged})
    return merged

@router.get('/leads',response_model=list[Record])
async def leads(): return await db.leads.find({},{'_id':0}).sort('created_at',-1).to_list(2000)

@router.patch('/leads/{lid}',response_model=Record)
async def update_lead(lid:str,body:StatusUpdate):
    if body.status not in LEAD_STATUSES: raise HTTPException(400,'Invalid lead status')
    result=await db.leads.update_one({'id':lid},{'$set':{'status':body.status,'updated_at':now()}})
    if not result.matched_count: raise HTTPException(404,'Lead not found')
    return await db.leads.find_one({'id':lid},{'_id':0})

@router.get('/orders',response_model=list[Record])
async def orders(): return await db.orders.find({},{'_id':0}).sort('created_at',-1).to_list(2000)

@router.patch('/orders/{oid}',response_model=Record)
async def update_order(oid:str,body:StatusUpdate):
    if body.status not in ORDER_STATUSES: raise HTTPException(400,'Invalid order status')
    result=await db.orders.update_one({'id':oid},{'$set':{'status':body.status,'updated_at':now()}})
    if not result.matched_count: raise HTTPException(404,'Order not found')
    return await db.orders.find_one({'id':oid},{'_id':0})

@router.get('/analytics')
async def analytics():
    grouped=await db.events.aggregate([{'$group':{'_id':{'name':'$name','audience':'$audience'},'count':{'$sum':1}}}]).to_list(100)
    return [{'name':r['_id']['name'],'audience':r['_id']['audience'],'count':r['count']} for r in grouped]

@router.get('/export')
async def export():
    products=await db.products.find({},{'_id':0}).to_list(2000)
    return {'schema_version':'1.0','exported_at':now(),'shopify_mapping':{'products':'Products','handle':'Handle','category':'Product Type / Collections','flavour':'Option1 Value','sku':'Variant SKU','price':'Variant Price','weight':'Variant Grams','ingredients':'Metafield: custom.ingredients','nutrition':'Metafield: custom.nutrition','bundles':'Bundle app configuration','reseller':'Customer tags + metafields','content':'Theme sections / metaobjects'},'products':products,'content':await db.content.find_one({'id':'site'},{'_id':0}),'orders':await db.orders.find({},{'_id':0}).to_list(2000),'leads':await db.leads.find({},{'_id':0}).to_list(2000)}