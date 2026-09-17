from datetime import datetime,timezone,timedelta
from fastapi import HTTPException
from db import db
from .economics import minor,flatten

def period_query(days=None,start=None,end=None):
    q={}
    try:
        if start:q['$gte']=datetime.fromisoformat(start.replace('Z','+00:00')).replace(tzinfo=timezone.utc).isoformat()
        elif days:q['$gte']=(datetime.now(timezone.utc)-timedelta(days=int(days)-1)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        if end:q['$lt']=(datetime.fromisoformat(end.replace('Z','+00:00')).replace(tzinfo=timezone.utc)+timedelta(days=1)).isoformat()
        if '$gte' in q and '$lt' in q and q['$gte']>=q['$lt']:raise ValueError()
    except (ValueError,TypeError):raise HTTPException(400,'Choose a valid date range with start before end')
    return {'created_at':q} if q else {}

def sale_query(rid=None,**period):
    query={'payment_status':'PAID','status':{'$ne':'CANCELLED'},'delivery_status':{'$ne':'RETURNED'},**period_query(**period)}
    if rid:query['reseller_id']=rid
    return query

async def commissions_for(orders):
    ids=[o['id'] for o in orders]
    return {c['order_id']:c for c in await db.commissions.find({'order_id':{'$in':ids},'status':{'$ne':'CANCELLED'}},{'_id':0}).to_list(len(ids)+1)}

def order_summary(order,ledger=None,private=False):
    public=['id','created_at','updated_at','name','status','payment_status','delivery_status','subtotal','items','reseller_id','order_channel','referral_code','referral_source','attributed_at','commission_exclusion','source_system']
    row={k:order.get(k) for k in public}
    snap=order.get('economics_snapshot',{})
    row.update({'units':snap.get('units',sum(p['units'] for p in flatten(order['items']))),'sales_minor':minor(order['subtotal']),'commission_minor':ledger['amount_minor'] if ledger else None,'commission_status':ledger['status'] if ledger else 'NOT_EARNED' if order['payment_status']!='PAID' else 'UNCONFIGURED','commission_id':ledger['id'] if ledger else None,'profit_minor':snap.get('estimated_gross_profit_minor'),'rule_snapshot':snap.get('parts',[])})
    if private:row.update({k:order.get(k) for k in ['email','mobile','address','city','pincode','payment_reference','attribution']})
    return row

async def sales(rid=None,channel=None,**period):
    query=sale_query(rid,**period)
    if channel:query['order_channel']=channel
    orders=await db.orders.find(query,{'_id':0}).sort('created_at',1).to_list(None)
    ledger=await commissions_for(orders);products={};trends={};customers={};profit=0;profit_known=bool(orders)
    for order in orders:
        c=ledger.get(order['id']);snap=order.get('economics_snapshot',{});parts=snap.get('parts') or flatten(order['items']);day=order['created_at'][:10]
        trend=trends.setdefault(day,{'date':day,'orders':0,'units':0,'sales_minor':0,'commission_minor':0})
        trend['orders']+=1;trend['sales_minor']+=minor(order['subtotal']);trend['units']+=sum(p['units'] for p in parts);trend['commission_minor']+=c['amount_minor'] if c else 0
        p=snap.get('estimated_gross_profit_minor')
        if p is None:profit_known=False
        else:profit+=p-((c['amount_minor']-snap['commission_minor']) if c and snap.get('commission_minor') is not None else 0)
        customer=customers.setdefault(order.get('customer_key',order['id']),{'name':order['name'],'orders':0,'sales_minor':0,'first_order':order['created_at'],'last_order':order['created_at']})
        customer['orders']+=1;customer['sales_minor']+=minor(order['subtotal']);customer['last_order']=order['created_at']
        seen=set();allocated_commission=0
        for index,part in enumerate(parts):
            if c:
                original=sum(x.get('commission_minor') or 0 for x in parts)
                share=round(c['amount_minor']*(part.get('commission_minor') or 0)/original) if original else 0
                actual_commission=c['amount_minor']-allocated_commission if index==len(parts)-1 else share
                allocated_commission+=actual_commission
            else:actual_commission=0
            product=products.setdefault(part['product_id'],{'product_id':part['product_id'],'title':part['title'],'units':0,'orders':0,'sales_minor':0,'commission_minor':0,'profit_minor':0,'cost_known':True})
            product['units']+=part['units'];product['sales_minor']+=part['sales_minor'];product['commission_minor']+=actual_commission
            if part['product_id'] not in seen:product['orders']+=1;seen.add(part['product_id'])
            if part.get('cost_minor') is None or part.get('commission_minor') is None or snap.get('other_cost_minor') is None:product['cost_known']=False;product['profit_minor']=None
            elif product['cost_known']:product['profit_minor']+=part['sales_minor']-part['cost_minor']-actual_commission-round(snap['other_cost_minor']*part['sales_minor']/max(snap['sales_minor'],1))
    values=list(customers.values())
    for c in values:c['repeat_customer']=c['orders']>1
    total=sum(minor(o['subtotal']) for o in orders)
    return {'orders':len(orders),'units':sum(v['units'] for v in trends.values()),'sales_minor':total,'commission_minor':sum(c['amount_minor'] for c in ledger.values()),'profit_minor':profit if profit_known else None,'average_order_value_minor':round(total/len(orders)) if orders else 0,'repeat_orders':sum(max(0,c['orders']-1) for c in values),'products':list(products.values()),'customers':values,'trend':list(trends.values()),'profit_note':'Estimated order gross profit, not commission or personal take-home income. Unavailable when historical cost/rule inputs are missing.','sales_basis':'Confirmed paid orders only; cancelled, refunded and returned orders excluded.'}

async def commission_totals(rid=None):
    match={'reseller_id':rid} if rid else {}
    groups=await db.commissions.aggregate([{'$match':match},{'$group':{'_id':'$status','amount_minor':{'$sum':'$amount_minor'},'count':{'$sum':1}}}]).to_list(20)
    result={s:0 for s in ['PENDING','APPROVED','PAYABLE','PAID','ADJUSTED','CANCELLED']}
    for g in groups:result[g['_id']]=g['amount_minor']
    adjustments=await db.commission_adjustments.find({**match,'affects_payout':True,'payout_id':None},{'_id':0,'difference_minor':1}).to_list(10000)
    reserved=await db.commissions.aggregate([{'$match':{**match,'status':'PAYABLE','payout_id':{'$ne':None}}},{'$group':{'_id':None,'amount':{'$sum':'$amount_minor'}}}]).to_list(1)
    result['unsettled_adjustments_minor']=sum(a['difference_minor'] for a in adjustments)
    result['reserved_minor']=reserved[0]['amount'] if reserved else 0
    result['available_minor']=max(0,result['PAYABLE']-result['reserved_minor']+result['unsettled_adjustments_minor'])
    payouts=await db.payouts.aggregate([{'$match':{**match,'status':'PAID'}},{'$group':{'_id':None,'total':{'$sum':'$amount_minor'}}}]).to_list(1)
    result['total_paid_minor']=payouts[0]['total'] if payouts else 0
    return result

async def referral_performance(rid):
    events=await db.referral_events.find({'reseller_id':rid},{'_id':0,'name':1,'visitor_hash':1}).to_list(None)
    counts={k:0 for k in ['link_click','product_view','add_to_cart','checkout_started']};visitors=set()
    for e in events:
        counts[e['name']]=counts.get(e['name'],0)+1
        if e['name']=='link_click':visitors.add(e['visitor_hash'])
    sold=await db.orders.find(sale_query(rid),{'_id':0,'subtotal':1,'referral_visitor_hash':1}).to_list(None)
    converted={o['referral_visitor_hash'] for o in sold if o.get('referral_visitor_hash')}
    return {**counts,'unique_visitors':len(visitors),'orders':len(sold),'sales_minor':sum(minor(o['subtotal']) for o in sold),'conversion_rate':round(len(converted&visitors)/len(visitors)*100,2) if visitors else None}

async def paginate(collection,query,page,limit,projection=None):
    total=await db[collection].count_documents(query)
    rows=await db[collection].find(query,projection or {'_id':0}).sort('created_at',-1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {'items':rows,'total':total,'page':page,'limit':limit}