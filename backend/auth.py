import os
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from db import db, uid, now
from models import Login

router = APIRouter(prefix='/api/auth')
def verify(plain, hashed):
    return bcrypt.checkpw(plain.encode(), hashed.encode())

async def seed_admin():
    email, password = os.environ['ADMIN_EMAIL'].lower(), os.environ['ADMIN_PASSWORD']
    existing = await db.users.find_one({'email':email},{'_id':0})
    if not existing:
        await db.users.insert_one({'id':uid(),'email':email,'name':'SANGLEY Admin','role':'admin','password_hash':bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),'created_at':now()})
    elif not verify(password, existing['password_hash']):
        await db.users.update_one({'email':email},{'$set':{'password_hash':bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()}})
    await db.users.create_index('email',unique=True)
    await db.login_attempts.create_index('identifier',unique=True)
    await db.login_attempts.create_index('expires_at',expireAfterSeconds=0)

def token(user, kind):
    return jwt.encode({'sub':user['id'],'email':user['email'],'type':kind,'exp':datetime.now(timezone.utc)+(timedelta(minutes=15) if kind=='access' else timedelta(days=7))},os.environ['JWT_SECRET'],algorithm='HS256')

def cookies(response,user,refresh=True):
    response.set_cookie('access_token',token(user,'access'),httponly=True,secure=True,samesite='none',max_age=900,path='/')
    if refresh:
        response.set_cookie('refresh_token',token(user,'refresh'),httponly=True,secure=True,samesite='none',max_age=604800,path='/')

def check_origin(request):
    origin=request.headers.get('origin')
    allowed={value.strip().rstrip('/') for value in os.environ['SANGLEY_TRUSTED_ORIGINS'].split(',')}
    if origin and origin.rstrip('/') not in allowed:
        raise HTTPException(403,'Request origin not allowed')

async def decode_user(value,kind):
    try:
        payload=jwt.decode(value,os.environ['JWT_SECRET'],algorithms=['HS256'])
        if payload.get('type')!=kind: raise ValueError()
        user=await db.users.find_one({'id':payload['sub'],'role':'admin'},{'_id':0,'password_hash':0})
        if not user: raise ValueError()
        return user
    except (jwt.InvalidTokenError,ValueError,KeyError):
        raise HTTPException(401,'Please sign in again')

async def admin(request: Request):
    if request.method not in ('GET','HEAD','OPTIONS'): check_origin(request)
    value=request.cookies.get('access_token')
    if not value:
        header=request.headers.get('Authorization','')
        value=header[7:] if header.startswith('Bearer ') else ''
    if not value: raise HTTPException(401,'Admin sign-in required')
    return await decode_user(value,'access')

@router.post('/login')
async def login(body:Login,request:Request,response:Response):
    check_origin(request)
    email=str(body.email).lower().strip()
    identifier=f'{request.client.host}:{email}'
    attempt=await db.login_attempts.find_one({'identifier':identifier},{'_id':0})
    if attempt and attempt.get('count',0)>=5 and attempt['expires_at'].replace(tzinfo=timezone.utc)>datetime.now(timezone.utc):
        raise HTTPException(429,'Too many attempts. Please wait 15 minutes.')
    user=await db.users.find_one({'email':email,'role':'admin'},{'_id':0})
    if not user or not verify(body.password,user['password_hash']):
        await db.login_attempts.update_one({'identifier':identifier},{'$inc':{'count':1},'$set':{'expires_at':datetime.now(timezone.utc)+timedelta(minutes=15)}},upsert=True)
        raise HTTPException(401,'Email or password is incorrect')
    await db.login_attempts.delete_one({'identifier':identifier})
    cookies(response,user)
    return {k:v for k,v in user.items() if k!='password_hash'}

@router.get('/me')
async def me(user=Depends(admin)): return user

@router.post('/refresh')
async def refresh(request:Request,response:Response):
    check_origin(request)
    user=await decode_user(request.cookies.get('refresh_token',''),'refresh')
    cookies(response,user,False)
    return user

@router.post('/logout')
async def logout(request:Request,response:Response):
    check_origin(request)
    response.delete_cookie('access_token',path='/',secure=True,httponly=True,samesite='none')
    response.delete_cookie('refresh_token',path='/',secure=True,httponly=True,samesite='none')
    return {'ok':True}