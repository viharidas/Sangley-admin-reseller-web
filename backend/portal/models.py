from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from typing import Optional, Literal
from datetime import date, datetime
from decimal import Decimal
import re

STATUSES=['PENDING','UNDER_REVIEW','APPROVED','REJECTED','HOLD','SUSPENDED','INACTIVE']
COMMUNITIES=['Family','Friends','Housing Society','Office','College','Local Community','WhatsApp Community','Social Media','Other']
def phone(value):
    value=re.sub(r'[\s()-]','',value)
    if re.fullmatch(r'[6-9]\d{9}',value): value='+91'+value
    if not re.fullmatch(r'\+[1-9]\d{9,14}',value): raise ValueError('Enter a valid mobile number with country code')
    return value

class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False,str_strip_whitespace=True,validate_default=True)

class Registration(Input):
    full_name:str=Field(min_length=2,max_length=100)
    email:EmailStr
    password:str=Field(min_length=10,max_length=72)
    mobile:str
    city:str=Field(min_length=2,max_length=100)
    address:str=Field(default='',max_length=500)
    community_type:str
    network_size:Optional[int]=Field(default=None,ge=0,le=10000000)
    whatsapp:str=''
    referral_source:str=Field(default='',max_length=200)
    pan:str=Field(default='',max_length=10)
    gst:str=Field(default='',max_length=15)
    account_name:str=Field(default='',max_length=120)
    account_number:str=Field(default='',max_length=30)
    ifsc:str=Field(default='',max_length=11)
    terms_accepted:bool
    @field_validator('mobile')
    @classmethod
    def mobile_valid(cls,v):return phone(v)
    @field_validator('whatsapp')
    @classmethod
    def wa_valid(cls,v):return phone(v) if v else ''
    @field_validator('password')
    @classmethod
    def password_valid(cls,v):
        if len(v.encode())>72:raise ValueError('Password exceeds the supported byte length')
        if not re.search(r'[A-Za-z]',v) or not re.search(r'\d',v):raise ValueError('Use at least ten characters with a letter and a number')
        return v
    @field_validator('community_type')
    @classmethod
    def community_valid(cls,v):
        if v not in COMMUNITIES:raise ValueError('Choose a supported community type')
        return v

class PasswordLogin(Input):
    email:EmailStr
    password:str=Field(min_length=1,max_length=72)
class PasswordChange(Input):
    current_password:str
    new_password:str=Field(min_length=10,max_length=72)
    @field_validator('new_password')
    @classmethod
    def valid(cls,v):return Registration.password_valid(v)
class ProfileUpdate(Input):
    full_name:Optional[str]=Field(default=None,min_length=2,max_length=100)
    city:Optional[str]=Field(default=None,min_length=2,max_length=100)
    address:Optional[str]=Field(default=None,max_length=500)
    community_type:Optional[str]=None
    network_size:Optional[int]=Field(default=None,ge=0,le=10000000)
    whatsapp:Optional[str]=None
    photo_file_id:Optional[str]=None
    account_name:Optional[str]=Field(default=None,max_length=120)
    account_number:Optional[str]=Field(default=None,max_length=30)
    ifsc:Optional[str]=Field(default=None,max_length=11)
    pan:Optional[str]=Field(default=None,max_length=10)
    gst:Optional[str]=Field(default=None,max_length=15)
    @field_validator('whatsapp')
    @classmethod
    def valid_wa(cls,v):return phone(v) if v else v

class Reason(Input):
    reason:str=Field(min_length=4,max_length=1000)
class ResellerState(Reason):
    status:Literal['PENDING','UNDER_REVIEW','APPROVED','REJECTED','HOLD','SUSPENDED','INACTIVE']
    tier:Optional[str]=None
class Rule(Input):
    name:str=Field(min_length=2,max_length=100)
    kind:Literal['PERCENTAGE','FIXED_PER_UNIT']
    rate:Decimal=Field(ge=0)
    product_ids:list[str]=[]
    variant_ids:list[str]=[]
    bundle_sizes:list[int]=[]
    tiers:list[str]=[]
    reseller_ids:list[str]=[]
    priority:int=Field(default=0,ge=0,le=1000)
    starts_at:Optional[datetime]=None
    ends_at:Optional[datetime]=None
    active:bool=True
    reason:str=Field(min_length=4,max_length=1000)
class FinancialOrder(Reason):
    payment_status:Literal['NOT_COLLECTED','PAID','REFUNDED']
    delivery_status:Literal['NOT_SHIPPED','PROCESSING','SHIPPED','DELIVERED','RETURNED']
    status:Literal['ENQUIRY','CONTACTED','CONFIRMED','FULFILLED','CANCELLED']
    payment_reference:str=Field(default='',max_length=150)
class Adjustment(Reason):
    new_amount:Decimal=Field(ge=0)
class PayoutCreate(Reason):
    reseller_id:str
    commission_ids:list[str]=Field(min_length=1,max_length=100)
    request_id:str=Field(min_length=8,max_length=100)
class PayoutUpdate(Reason):
    status:Literal['APPROVED','PAID','FAILED','ADJUSTED']
    payment_reference:str=Field(default='',max_length=150)
    payment_date:Optional[date]=None
    notes:str=Field(default='',max_length=2000)
    actual_payment_confirmed:bool=False
class Target(Input):
    reseller_id:str
    month:str=Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    sales_target:Optional[Decimal]=Field(default=None,ge=0)
    orders_target:Optional[int]=Field(default=None,ge=0)
    units_target:Optional[int]=Field(default=None,ge=0)
    commission_target:Optional[Decimal]=Field(default=None,ge=0)
    reason:str=Field(min_length=4,max_length=1000)
class Ticket(Input):
    subject:str=Field(min_length=3,max_length=150)
    category:Literal['ORDERS','COMMISSION','PAYOUTS','ACCOUNT','PRODUCTS','OTHER']
    message:str=Field(min_length=5,max_length=5000)
    attachment_ids:list[str]=Field(default=[],max_length=3)
class TicketUpdate(Input):
    status:Optional[Literal['OPEN','IN_PROGRESS','RESOLVED','CLOSED']]=None
    message:str=Field(default='',max_length=5000)
class Marketing(Input):
    title:str=Field(min_length=2,max_length=150)
    category:Literal['PRODUCT','WHATSAPP','INSTAGRAM','OFFERS','CATALOGUE','SELLING_TIPS']
    description:str=Field(default='',max_length=2000)
    file_id:Optional[str]=None
    url:str=''
    active:bool=True
    @field_validator('url')
    @classmethod
    def safe(cls,v):
        if v and not v.startswith('https://'):raise ValueError('Use a public HTTPS link')
        return v
class Announcement(Input):
    title:str=Field(min_length=2,max_length=150)
    message:str=Field(min_length=2,max_length=2000)
    reseller_id:Optional[str]=None
    type:Literal['ANNOUNCEMENT','NEW_PRODUCT','NEW_OFFER','REORDER_REMINDER']='ANNOUNCEMENT'