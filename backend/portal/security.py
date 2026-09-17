import os,json,secrets,hashlib
from datetime import datetime,timezone,timedelta
import jwt,bcrypt
from cryptography.fernet import Fernet
from fastapi import Request,HTTPException,Depends
from auth import admin,check_origin
from db import db,now,uid
from .settings import settings

def encrypt(data):return Fernet(os.environ['PORTAL_DATA_KEY'].encode()).encrypt(json.dumps(data).encode()).decode()
def decrypt(data):return json.loads(Fernet(os.environ['PORTAL_DATA_KEY'].encode()).decrypt(data.encode())) if data else {}
def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def public_profile(profile):
    p={k:v for k,v in profile.items() if k not in {'_id','private_details'}}
    details=decrypt(profile.get('private_details'))
    p['payout_details']={k:('••••'+v[-4:] if k in ('account_number','pan','gst') and v else v) for k,v in details.items()}
    if p.get('referral_code'):p['referral_url']=os.environ['FRONTEND_URL'].rstrip('/')+'/r/'+p['referral_code']
    return p

async def throttle(key,limit=5,minutes=15):
    expires=datetime.now(timezone.utc)+timedelta(minutes=minutes)
    row=await db.login_attempts.find_one({'identifier':key},{'_id':0})
    if row and row.get('expires_at').replace(tzinfo=timezone.utc)>datetime.now(timezone.utc) and row.get('count',0)>=limit:
        raise HTTPException(429,'Too many attempts. Please wait before trying again.')
    if row and row['expires_at'].replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc):await db.login_attempts.delete_one({'identifier':key})
    await db.login_attempts.update_one({'identifier':key},{'$inc':{'count':1},'$setOnInsert':{'expires_at':expires}},upsert=True)

def set_access(response,user,sid):
    token=jwt.encode({'sub':user['id'],'sid':sid,'role':'reseller','ver':user.get('session_version',0),'type':'reseller_access','exp':datetime.now(timezone.utc)+timedelta(minutes=15)},os.environ['JWT_SECRET'],algorithm='HS256')
    response.set_cookie('reseller_access',token,max_age=900,httponly=True,secure=True,samesite='none',path='/')

async def create_session(response,user):
    sid=uid();refresh=secrets.token_urlsafe(48)
    await db.portal_sessions.insert_one({'id':sid,'user_id':user['id'],'token_hash':digest(refresh),'version':user.get('session_version',0),'revoked':False,'expires_at':datetime.now(timezone.utc)+timedelta(days=7),'created_at':now()})
    set_access(response,user,sid)
    response.set_cookie('reseller_refresh',refresh,max_age=604800,httponly=True,secure=True,samesite='none',path='/')

async def applicant(request:Request):
    if request.method not in ('GET','HEAD','OPTIONS'):check_origin(request)
    token=request.cookies.get('reseller_access','')
    try:
        payload=jwt.decode(token,os.environ['JWT_SECRET'],algorithms=['HS256'])
        if payload.get('type')!='reseller_access':raise ValueError()
        user=await db.users.find_one({'id':payload['sub'],'role':'reseller'},{'_id':0,'password_hash':0})
        session=await db.portal_sessions.find_one({'id':payload['sid'],'revoked':False,'expires_at':{'$gt':datetime.now(timezone.utc)}},{'_id':0})
        if not user or not session or user.get('session_version',0)!=payload.get('ver'):raise ValueError()
        profile=await db.resellers.find_one({'user_id':user['id']},{'_id':0})
        if not profile:raise ValueError()
        return {'user':user,'profile':profile,'session_id':session['id']}
    except (jwt.InvalidTokenError,ValueError,KeyError):raise HTTPException(401,'Please sign in to your reseller account')

async def reseller(auth=Depends(applicant)):
    if auth['profile']['status']!='APPROVED':raise HTTPException(403,'Your reseller account is not approved for business access. View your application status.')
    return auth

def permit(permission):
    async def check(user=Depends(admin)):
        config=await settings()
        if permission not in config['roles_permissions'].get(user['role'],[]):raise HTTPException(403,'You do not have permission for this action')
        return user
    return check

async def file_user(request:Request):
    if request.cookies.get('access_token') or request.headers.get('Authorization'):
        try:return {'user':await admin(request),'profile':None}
        except HTTPException:pass
    return await applicant(request)