from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / '.env')
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from db import client
from seed import seed_content
from auth import router as auth_router, seed_admin
from commerce import router as commerce_router
from admin_routes import router as admin_router
from portal.settings import seed_portal
from portal.financial import reconcile_paid_payouts
from portal.auth_routes import router as reseller_auth_router
from portal.reseller_routes import router as reseller_router
from portal.admin_routes import router as business_router
from portal.finance_routes import router as finance_router
from portal.referrals import router as referral_router
from portal.files import router as files_router

@asynccontextmanager
async def lifespan(app):
    await seed_admin()
    await seed_content()
    await seed_portal()
    await reconcile_paid_payouts()
    yield
    client.close()

app=FastAPI(title='SANGLEY Commerce & Community',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=[value.strip().rstrip('/') for value in os.environ['SANGLEY_TRUSTED_ORIGINS'].split(',')],allow_credentials=True,allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type','Authorization'])
app.include_router(auth_router)
app.include_router(commerce_router)
app.include_router(admin_router)
app.include_router(reseller_auth_router)
app.include_router(reseller_router)
app.include_router(business_router)
app.include_router(finance_router)
app.include_router(referral_router)
app.include_router(files_router)