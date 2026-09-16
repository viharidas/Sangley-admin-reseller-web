from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError
from db import db, uid, now
from models import Product, Quote, Order, Lead, Event, Record

router=APIRouter(prefix='/api')

@router.get('/')
async def health(): return {'brand':'SANGLEY','status':'ready'}

@router.get('/products',response_model=list[Product])
async def products():
    return await db.products.find({},{'_id':0}).sort('featured_order',1).to_list(200)

@router.get('/products/{handle}',response_model=Product)
async def product(handle:str):
    result=await db.products.find_one({'handle':handle},{'_id':0})
    if not result: raise HTTPException(404,'This flavour could not be found')
    return result

@router.get('/content',response_model=Record)
async def content():
    return await db.content.find_one({'id':'site'},{'_id':0})

async def calculate(body:Quote):
    site=await db.content.find_one({'id':'site'},{'_id':0})
    products={p['id']:p for p in await db.products.find({},{'_id':0}).to_list(200)}
    lines=[]
    for line in body.items:
        if line.bundle_size is not None:
            bundle=next((b for b in site['bundles'] if b['size']==line.bundle_size and b.get('enabled')),None)
            if not bundle: raise HTTPException(400,'This box size is not available')
            if not line.selections or any(not isinstance(q,int) or isinstance(q,bool) or q<1 for q in line.selections.values()) or sum(line.selections.values())!=line.bundle_size:
                raise HTTPException(400,f'Please choose exactly {line.bundle_size} packs')
            if not bundle.get('mix_match',True) and len(line.selections)>1:
                raise HTTPException(400,'This box is available in one flavour only')
            selected=[]
            for pid,q in line.selections.items():
                p=products.get(pid)
                if not p or not p['available']: raise HTTPException(400,'A selected flavour is unavailable')
                selected.append({'product_id':pid,'title':p['title'],'quantity':q,'sku':p['sku'],'unit_price':p['price']})
            price=bundle.get('price')
            if price is None: price=sum(p['unit_price']*p['quantity'] for p in selected)
            lines.append({'title':f'SANGLEY Box · {line.bundle_size} packs','bundle_size':line.bundle_size,'selections':selected,'quantity':line.quantity,'unit_price':round(price,2),'line_total':round(price*line.quantity,2),'image':products[next(iter(line.selections))]['images'][0] if products[next(iter(line.selections))]['images'] else ''})
        else:
            p=products.get(line.product_id)
            if not p or not p['available']: raise HTTPException(400,'This flavour is currently unavailable')
            lines.append({'product_id':p['id'],'title':p['title'],'sku':p['sku'],'quantity':line.quantity,'unit_price':p['price'],'line_total':round(p['price']*line.quantity,2),'image':p['images'][0] if p['images'] else ''})
    return {'items':lines,'subtotal':round(sum(x['line_total'] for x in lines),2),'currency':'INR','shipping':None,'shipping_text':site['shipping_text'],'checkout_mode':'enquiry'}

@router.post('/cart/quote')
async def quote(body:Quote): return await calculate(body)

@router.post('/orders',response_model=Record)
async def order(body:Order):
    if not body.consent: raise HTTPException(400,'Please consent to being contacted about your enquiry')
    previous=await db.orders.find_one({'request_id':body.request_id},{'_id':0})
    if previous: return {'id':previous['id'],'subtotal':previous['subtotal'],'status':previous['status'],'message':'Your order enquiry has been received. No payment has been taken.'}
    priced=await calculate(body)
    doc={'id':'SNG-'+uid()[:8].upper(),**body.model_dump(exclude={'items'}),**priced,'status':'ENQUIRY','payment_status':'NOT_COLLECTED','created_at':now()}
    try: await db.orders.insert_one(doc.copy())
    except DuplicateKeyError:
        previous=await db.orders.find_one({'request_id':body.request_id},{'_id':0})
        return {'id':previous['id'],'subtotal':previous['subtotal'],'status':previous['status'],'message':'Your order enquiry has been received. No payment has been taken.'}
    return {'id':doc['id'],'subtotal':doc['subtotal'],'status':doc['status'],'message':'Your order enquiry has been received. No payment has been taken.'}

@router.post('/leads',response_model=Record)
async def lead(body:Lead):
    if not body.consent: raise HTTPException(400,'Please consent to being contacted')
    doc={'id':uid(),**body.model_dump(),'status':'NEW LEAD','created_at':now()}
    await db.leads.insert_one(doc.copy())
    return {'id':doc['id'],'message':'You’re on the list. Our team will get in touch to discuss your next step.'}

@router.post('/events')
async def event(body:Event):
    allowed={'page_view','product_view','add_to_cart','checkout','purchase','order_enquiry','bundle_builder_started','bundle_completed','reseller_cta_click','whatsapp_click','reseller_lead','consumer_lead','starter_kit_selection','search'}
    if body.name not in allowed: raise HTTPException(400,'Unknown event')
    await db.events.insert_one({'id':uid(),**body.model_dump(),'created_at':now()})
    return {'ok':True}