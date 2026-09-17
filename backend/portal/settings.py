from db import db,now
from pydantic import Field
from .models import Input
from typing import Literal, Optional
from decimal import Decimal

DEFAULT_PERMISSIONS={
 'admin':['resellers','orders','finance','catalogue','settings','marketing','support','audit'],
 'super_admin':['resellers','orders','finance','catalogue','settings','marketing','support','audit','staff'],
 'operations':['resellers','orders','catalogue','marketing','support'],
 'finance':['finance','orders','audit'], 'support':['support','resellers'], 'reseller':[], 'customer':[]}

class BusinessSettings(Input):
    referral_policy:Literal['FIRST','LAST','OWNERSHIP']='FIRST'
    attribution_days:int=Field(default=30,ge=1,le=365)
    repeat_attribution:bool=False
    campaign_policies:dict[str,Literal['FIRST','LAST','OWNERSHIP']]={}
    required_fields:list[str]=['full_name','email','mobile','city','community_type','terms_accepted']
    tiers:list[str]=['STARTER','ACTIVE','GROWTH','PRO']
    product_costs:dict[str,Decimal]={}
    other_cost_per_order:Optional[Decimal]=Field(default=None,ge=0)
    minimum_payout:Decimal=Field(default=0,ge=0)
    support_email:str=''
    support_phone:str=''
    support_whatsapp:str=''
    registration_terms:str='I agree that my application is subject to review. Commission and payouts depend on approved rules and eligible orders; no income is guaranteed.'
    payout_notes:str='Payouts are recorded manually after actual payment. Approval alone is not a bank transfer.'
    shipping_notes:str=''
    tax_notes:str=''
    notification_preferences:dict[str,bool]={'in_app':True,'email':False,'whatsapp':False}
    roles_permissions:dict[str,list[str]]=DEFAULT_PERMISSIONS

async def settings():
    return await db.business_settings.find_one({'id':'portal'},{'_id':0})

async def seed_portal():
    data=BusinessSettings().model_dump(mode='json')
    await db.business_settings.update_one({'id':'portal'},{'$setOnInsert':{'id':'portal',**data,'created_at':now(),'updated_at':now()}},upsert=True)
    indexes={
      'resellers':[('id',True),('user_id',True),('mobile',True)],
      'portal_sessions':[('id',True),('user_id',False)],
      'referral_sessions':[('token_hash',True),('reseller_id',False)],
      'referral_events':[('reseller_id',False),('created_at',False)],
      'commissions':[('id',True),('order_id',True),('reseller_id',False),('payout_id',False)],
      'payouts':[('id',True),('request_id',True),('reseller_id',False)],
      'commission_adjustments':[('id',True),('reseller_id',False)],
      'reseller_targets':[('id',True)],'portal_notifications':[('reseller_id',False)],
      'support_tickets':[('id',True),('reseller_id',False)],'marketing_assets':[('id',True)],
      'portal_files':[('id',True)],'audit_logs':[('id',True),('created_at',False),('entity_id',False)],
      'customer_ownership':[('customer_key',True)],'financial_locks':[('id',True)]}
    for collection,fields in indexes.items():
        for field,unique in fields:await db[collection].create_index(field,unique=unique)
    await db.resellers.create_index('referral_code',unique=True,sparse=True)
    await db.resellers.create_index('reseller_number',unique=True,sparse=True)
    await db.orders.create_index([('reseller_id',1),('created_at',-1)])
    await db.orders.create_index('customer_key')
    await db.reseller_targets.create_index([('reseller_id',1),('month',1)],unique=True)
    await db.portal_sessions.create_index('expires_at',expireAfterSeconds=0)
    await db.referral_sessions.create_index('expires_at',expireAfterSeconds=0)
    await db.customer_ownership.create_index('first_paid_order_id',sparse=True)