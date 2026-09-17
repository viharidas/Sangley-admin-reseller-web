from decimal import Decimal,ROUND_HALF_UP
from datetime import datetime,timezone
from db import db,now
from .settings import settings

def minor(value):return int((Decimal(str(value))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def rounded(value):return int(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def flatten(items):
    parts=[]
    for i,line in enumerate(items):
        total=minor(line['line_total'])
        if line.get('bundle_size'):
            selected=line['selections'];weights=[Decimal(str(s['unit_price']))*s['quantity'] for s in selected];weight=sum(weights);allocated=0
            for j,s in enumerate(selected):
                share=total-allocated if j==len(selected)-1 else rounded(Decimal(total)*weights[j]/weight) if weight else total//len(selected)
                allocated+=share
                parts.append({'product_id':s['product_id'],'variant_id':s['product_id'],'title':s['title'],'sku':s['sku'],'units':s['quantity']*line['quantity'],'sales_minor':share,'bundle_size':line['bundle_size'],'line_index':i})
        else:parts.append({'product_id':line['product_id'],'variant_id':line['product_id'],'title':line['title'],'sku':line['sku'],'units':line['quantity'],'sales_minor':total,'bundle_size':None,'line_index':i})
    return parts

def applies(rule,part,reseller,stamp):
    for key,value in [('product_ids',part['product_id']),('variant_ids',part['variant_id']),('bundle_sizes',part['bundle_size']),('tiers',reseller.get('tier')),('reseller_ids',reseller['id'])]:
        if rule.get(key) and value not in rule[key]:return False
    for field,op in [('starts_at','start'),('ends_at','end')]:
        if rule.get(field):
            dt=datetime.fromisoformat(rule[field].replace('Z','+00:00'))
            if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
            if (op=='start' and stamp<dt) or (op=='end' and stamp>dt):return False
    return True

async def snapshot(items,reseller=None):
    config=await settings();parts=flatten(items);stamp=datetime.now(timezone.utc)
    rules=await db.commission_rules.find({'active':True},{'_id':0}).to_list(2000) if reseller else []
    rules.sort(key=lambda r:(r['priority'],sum(bool(r.get(k)) for k in ['product_ids','variant_ids','bundle_sizes','tiers','reseller_ids']),r['created_at']),reverse=True)
    configured=bool(reseller)
    costs_known=config.get('other_cost_per_order') is not None
    for part in parts:
        rule=next((r for r in rules if applies(r,part,reseller,stamp)),None) if reseller else None
        if rule:
            value=rounded(Decimal(part['sales_minor'])*Decimal(rule['rate'])/100) if rule['kind']=='PERCENTAGE' else minor(rule['rate'])*part['units']
            part.update({'rule_id':rule['id'],'rule_version':rule['version'],'rule_name':rule['name'],'commission_type':rule['kind'],'commission_rate':rule['rate'],'commission_minor':value})
        else:
            part.update({'rule_id':None,'commission_minor':0 if reseller is None else None});configured=False if reseller else configured
        cost=config['product_costs'].get(part['product_id'])
        part['cost_minor']=minor(cost)*part['units'] if cost is not None else None
        if cost is None:costs_known=False
    commission=sum(p['commission_minor'] for p in parts) if configured else (0 if not reseller else None)
    total=sum(p['sales_minor'] for p in parts)
    cost_total=sum(p['cost_minor'] for p in parts) if costs_known else None
    other=minor(config['other_cost_per_order']) if config.get('other_cost_per_order') is not None else None
    profit=total-cost_total-commission-other if costs_known and commission is not None else None
    return {'created_at':now(),'configured':configured,'parts':parts,'sales_minor':total,'units':sum(p['units'] for p in parts),'commission_minor':commission,'product_cost_minor':cost_total,'other_cost_minor':other,'estimated_gross_profit_minor':profit,'profit_basis':'Order selling value minus configured product costs, commission and other costs. Not reseller take-home income.'}