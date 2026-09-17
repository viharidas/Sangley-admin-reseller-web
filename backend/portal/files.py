import os,secrets,asyncio
from io import BytesIO
from urllib.parse import quote
import httpx
from PIL import Image
from fastapi import APIRouter,Request,Response,Depends,HTTPException,Query
from db import db,uid,now
from .security import file_user
from .audit import audit
from .settings import settings

router=APIRouter(prefix='/api/portal-files')
storage_key=None
storage_lock=asyncio.Lock()
TYPES={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','application/pdf':'pdf','video/mp4':'mp4'}

def storage_url():
    base=os.environ.get('INTEGRATION_PROXY_URL','').strip()
    if not base:raise HTTPException(503,'File storage connection is not configured')
    return base.rstrip('/')+'/objstore/api/v1/storage'

async def init_storage(force=False):
    global storage_key
    async with storage_lock:
        if storage_key and not force:return storage_key
        async with httpx.AsyncClient(timeout=35) as client:
            res=await client.post(storage_url()+'/init',json={'emergent_key':os.environ['EMERGENT_LLM_KEY']});res.raise_for_status();storage_key=res.json()['storage_key'];return storage_key

async def storage_call(method,path,data=None,content_type=None,retry=True):
    try:
        key=await init_storage()
        headers={'X-Storage-Key':key}
        if content_type:headers['Content-Type']=content_type
        async with httpx.AsyncClient(timeout=90) as client:
            response=await client.request(method,storage_url()+'/objects/'+quote(path,safe='/'),headers=headers,content=data)
        if response.status_code==404 and retry:
            await init_storage(True);return await storage_call(method,path,data,content_type,False)
        response.raise_for_status();return response
    except HTTPException:raise
    except Exception:raise HTTPException(503,'File storage is temporarily unavailable. Please retry; your file has not been published.')

@router.post('')
async def upload(request:Request,filename:str=Query(...,min_length=1,max_length=200),purpose:str=Query(...,pattern='^(marketing|support|avatar)$'),auth=Depends(file_user)):
    user=auth['user'];config=await settings()
    if purpose=='marketing' and 'marketing' not in config['roles_permissions'].get(user['role'],[]):raise HTTPException(403,'Only authorised staff can upload marketing assets')
    if auth['profile'] and auth['profile']['status']!='APPROVED':raise HTTPException(403,'An approved reseller account is required to upload files')
    kind=request.headers.get('content-type','').split(';')[0]
    if kind not in TYPES or purpose=='avatar' and not kind.startswith('image/'):raise HTTPException(415,'Use JPG, PNG, WebP, PDF or MP4; avatars must be images')
    max_size=5*1024*1024 if purpose=='avatar' else 25*1024*1024
    data=bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data)>max_size:raise HTTPException(413,'This file exceeds the upload limit (5MB avatars, 25MB other files)')
    if not data:raise HTTPException(400,'The file is empty')
    raw=bytes(data)
    try:
        if kind.startswith('image/'):
            with Image.open(BytesIO(raw)) as im:
                if im.width*im.height>25000000:raise ValueError()
                actual=Image.MIME.get(im.format)
                if actual!=kind:raise ValueError()
                im.verify()
        elif kind=='application/pdf' and not raw.startswith(b'%PDF-'):raise ValueError()
        elif kind=='video/mp4' and (len(raw)<12 or raw[4:8]!=b'ftyp'):raise ValueError()
    except Exception:raise HTTPException(415,'File contents do not match the selected format')
    fid=uid();path=f'{os.environ["STORAGE_APP_NAME"]}/uploads/{user["id"]}/{fid}.{TYPES[kind]}'
    result=await storage_call('PUT',path,raw,kind)
    doc={'id':fid,'owner_id':user['id'],'purpose':purpose,'storage_path':result.json()['path'],'original_filename':filename,'content_type':kind,'size':len(raw),'is_deleted':False,'created_at':now()}
    await db.portal_files.insert_one(doc.copy());await audit(user,'FILE_UPLOADED','portal_files',fid,None,{k:v for k,v in doc.items() if k!='storage_path'},'Durable object storage upload')
    return {k:v for k,v in doc.items() if k!='storage_path'}

@router.get('/{fid}')
async def download(fid:str,download:bool=False,auth=Depends(file_user)):
    row=await db.portal_files.find_one({'id':fid,'is_deleted':False},{'_id':0})
    if not row:raise HTTPException(404,'File not found')
    user=auth['user'];staff=user['role'] in ['admin','super_admin'];owner=row['owner_id']==user['id']
    approved=auth['profile'] and auth['profile']['status']=='APPROVED'
    asset=await db.marketing_assets.find_one({'file_id':fid,'active':True},{'_id':0,'id':1}) if row['purpose']=='marketing' else None
    if not (staff or owner or approved and asset):raise HTTPException(404,'File not found')
    response=await storage_call('GET',row['storage_path'])
    disposition='attachment' if download or not row['content_type'].startswith('image/') else 'inline'
    return Response(content=response.content,media_type=row['content_type'],headers={'Content-Disposition':f"{disposition}; filename*=UTF-8''{quote(row['original_filename'])}",'X-Content-Type-Options':'nosniff','Cache-Control':'private, max-age=60','Content-Security-Policy':"default-src 'none'; sandbox"})