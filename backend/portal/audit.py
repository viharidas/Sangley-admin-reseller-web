import copy
from db import db,now,uid
from fastapi import HTTPException
from pymongo import ReturnDocument

PRIVATE={'password','password_hash','current_password','new_password','private_details','account_number','pan','gst','ifsc','password_reset_token','token_hash'}
def safe(value):
    if isinstance(value,dict):return {k:('[REDACTED]' if k in PRIVATE else safe(v)) for k,v in value.items() if k!='_id'}
    if isinstance(value,list):return [safe(v) for v in value]
    return value

async def audit(actor,action,entity,entity_id,old,new,reason='',outcome='COMPLETED'):
    record={'id':uid(),'actor_id':actor.get('id','system'),'actor_name':actor.get('name',actor.get('email','System')),'actor_role':actor.get('role','system'),'action':action,'entity':entity,'entity_id':entity_id,'old_value':safe(old),'new_value':safe(new),'reason':reason,'outcome':outcome,'created_at':now()}
    await db.audit_logs.insert_one(copy.deepcopy(record))
    return record['id']

async def change(collection,query,updates,actor,action,reason):
    old=await db[collection].find_one(query,{'_id':0})
    if not old:raise HTTPException(404,'The requested record was not found or has changed')
    aid=await audit(actor,action,collection,old['id'],old,{**old,**updates},reason,'PENDING')
    query={**query,'updated_at':old['updated_at']} if 'updated_at' in old else {**query,'updated_at':{'$exists':False}}
    result=await db[collection].find_one_and_update(query,{'$set':{**updates,'updated_at':now()}},projection={'_id':0},return_document=ReturnDocument.AFTER)
    await db.audit_logs.update_one({'id':aid},{'$set':{'outcome':'COMPLETED' if result else 'CONFLICT'}})
    if not result:raise HTTPException(409,'This record changed. Refresh and try again.')
    return result

async def notify(reseller_id,kind,title,message,link=''):
    await db.portal_notifications.insert_one({'id':uid(),'reseller_id':reseller_id,'type':kind,'title':title,'message':message,'link':link,'read':False,'created_at':now()})