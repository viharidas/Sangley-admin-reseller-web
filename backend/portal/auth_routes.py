from fastapi import APIRouter,Request,Response,Depends,HTTPException
from pymongo.errors import DuplicateKeyError
from datetime import datetime,timezone
from db import db,uid,now
from auth import check_origin
from .models import Registration,PasswordLogin,PasswordChange,Input
from .security import encrypt,public_profile,throttle,create_session,applicant,set_access,digest
from .settings import settings
from .audit import audit
from pydantic import EmailStr
import bcrypt

router=APIRouter(prefix='/api/reseller/auth')
PRIVATE=['pan','gst','account_name','account_number','ifsc']

@router.get('/capabilities')
async def capabilities():
    config=await settings()
    return {'password_login':True,'mobile_otp':False,'email_reset':False,'required_fields':config['required_fields'],'registration_terms':config['registration_terms'],'delivery_note':'Your SMS and email providers have not yet been identified or connected.'}

@router.post('/register')
async def register(body:Registration,request:Request,response:Response):
    check_origin(request);await throttle('register:'+request.client.host,10,60)
    if not body.terms_accepted:raise HTTPException(400,'Please accept the application terms')
    config=await settings();data=body.model_dump();email=str(body.email).lower()
    for key in config['required_fields']:
        if key in data and data[key] in ('',None,False):raise HTTPException(422,f'Please complete {key.replace("_"," ")}')
    if await db.users.find_one({'email':email},{'_id':0,'id':1}) or await db.resellers.find_one({'mobile':body.mobile},{'_id':0,'id':1}):raise HTTPException(409,'An account already uses these contact details. Try signing in.')
    user={'id':uid(),'email':email,'name':body.full_name,'role':'reseller','password_hash':bcrypt.hashpw(body.password.encode(),bcrypt.gensalt()).decode(),'session_version':0,'created_at':now(),'updated_at':now()}
    profile={'id':uid(),'user_id':user['id'],'email':email,**{k:v for k,v in data.items() if k not in PRIVATE+['password','email']},'private_details':encrypt({k:data[k] for k in PRIVATE}),'status':'PENDING','tier':config['tiers'][0] if config['tiers'] else '','mobile_verified':False,'terms_accepted_at':now(),'photo_file_id':None,'created_at':now(),'updated_at':now()}
    try:
        await db.users.insert_one(user.copy())
        try:await db.resellers.insert_one(profile.copy())
        except Exception:
            await db.users.delete_one({'id':user['id']});raise
    except DuplicateKeyError:raise HTTPException(409,'An account already uses these contact details')
    await audit(user,'RESELLER_APPLIED','resellers',profile['id'],None,public_profile(profile),'Application submitted')
    await create_session(response,user)
    return {'user':{k:v for k,v in user.items() if k!='password_hash'},'profile':public_profile(profile)}

@router.post('/login')
async def login(body:PasswordLogin,request:Request,response:Response):
    check_origin(request);email=str(body.email).lower();key=f'portal-login:{email}'
    await throttle(key)
    user=await db.users.find_one({'email':email,'role':'reseller'},{'_id':0})
    if not user or len(body.password.encode())>72 or not bcrypt.checkpw(body.password.encode(),user['password_hash'].encode()):raise HTTPException(401,'Email or password is incorrect')
    await db.login_attempts.delete_one({'identifier':key})
    profile=await db.resellers.find_one({'user_id':user['id']},{'_id':0})
    if not profile:raise HTTPException(401,'Your account could not be found')
    await create_session(response,user)
    return {'user':{k:v for k,v in user.items() if k!='password_hash'},'profile':public_profile(profile)}

@router.get('/me')
async def me(auth=Depends(applicant)):
    return {'user':auth['user'],'profile':public_profile(auth['profile'])}

@router.post('/refresh')
async def refresh(request:Request,response:Response):
    check_origin(request)
    row=await db.portal_sessions.find_one({'token_hash':digest(request.cookies.get('reseller_refresh','')),'revoked':False,'expires_at':{'$gt':datetime.now(timezone.utc)}},{'_id':0})
    if not row:raise HTTPException(401,'Please sign in again')
    user=await db.users.find_one({'id':row['user_id'],'role':'reseller'},{'_id':0,'password_hash':0})
    if not user or row['version']!=user.get('session_version',0):raise HTTPException(401,'Please sign in again')
    set_access(response,user,row['id'])
    return {'ok':True}

@router.post('/logout')
async def logout(request:Request,response:Response):
    check_origin(request)
    refresh=request.cookies.get('reseller_refresh')
    if refresh:await db.portal_sessions.update_many({'token_hash':digest(refresh)},{'$set':{'revoked':True}})
    for name in ['reseller_access','reseller_refresh']:response.delete_cookie(name,path='/',httponly=True,secure=True,samesite='none')
    return {'ok':True}

@router.post('/change-password')
async def change_password(body:PasswordChange,response:Response,auth=Depends(applicant)):
    user=await db.users.find_one({'id':auth['user']['id']},{'_id':0})
    if len(body.current_password.encode())>72 or not bcrypt.checkpw(body.current_password.encode(),user['password_hash'].encode()):raise HTTPException(400,'Current password is incorrect')
    await db.users.update_one({'id':user['id']},{'$set':{'password_hash':bcrypt.hashpw(body.new_password.encode(),bcrypt.gensalt()).decode(),'updated_at':now()},'$inc':{'session_version':1}})
    await db.portal_sessions.update_many({'user_id':user['id']},{'$set':{'revoked':True}})
    user['session_version']=user.get('session_version',0)+1
    await create_session(response,user)
    await audit(auth['user'],'PASSWORD_CHANGED','users',user['id'],None,{'sessions_revoked':True},'Account owner changed password')
    return {'ok':True}

class Recovery(Input):email:EmailStr
@router.post('/forgot-password')
async def recovery(body:Recovery,request:Request):
    check_origin(request);await throttle('reset:'+request.client.host,5,30)
    raise HTTPException(503,'Password-reset email delivery is not connected yet. Please contact SANGLEY support. No email has been sent.')

@router.post('/otp/send')
@router.post('/otp/verify')
async def otp(request:Request):
    check_origin(request);await throttle('otp:'+request.client.host,5,30)
    raise HTTPException(503,'Mobile OTP is unavailable until your messaging provider is connected. Please use email and password.')