from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, Literal

class Product(BaseModel):
    id: str
    handle: str = Field(pattern=r'^[a-z0-9-]+$')
    title: str = Field(min_length=1, max_length=120)
    flavour: str
    category: str = 'bhadang'
    vendor: str = 'SANGLEY'
    sku: str
    price: float = Field(ge=0)
    mrp: Optional[float] = Field(default=None, ge=0)
    weight: int = Field(default=200, gt=0)
    description: str = ''
    personality: str = ''
    flavour_profile: str = ''
    ingredients: str = ''
    nutrition: str = ''
    storage: str = ''
    images: list[str] = []
    image_labels: list[str] = []
    concept_images: bool = True
    available: bool = True
    badge: str = ''
    color: str = '#ed482b'
    background: str = '#f4dfd1'
    seo_title: str = ''
    seo_description: str = ''
    featured_order: int = 0
    sales_count: int = 0
    created_at: str = ''
    metafields: dict = {}

class Login(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

class Line(BaseModel):
    product_id: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=100)
    bundle_size: Optional[int] = None
    selections: dict[str, int] = {}

class Quote(BaseModel):
    items: list[Line] = Field(min_length=1, max_length=50)

class Order(Quote):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    mobile: str = Field(pattern=r'^\+?[0-9 ]{10,15}$')
    address: str = Field(min_length=5, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    pincode: str = Field(pattern=r'^[1-9][0-9]{5}$')
    consent: bool
    request_id: str = Field(min_length=8, max_length=100)
    attribution: dict[str, str] = {}

class Lead(BaseModel):
    type: Literal['reseller','consumer','whatsapp'] = 'reseller'
    name: str = Field(min_length=2, max_length=120)
    mobile: str = Field(pattern=r'^\+?[0-9 ]{10,15}$')
    email: Optional[EmailStr] = None
    city: str = Field(min_length=2, max_length=100)
    community_type: str = ''
    network_size: str = ''
    starter_option: str = ''
    whatsapp: str = ''
    message: str = Field(default='', max_length=2000)
    consent: bool
    attribution: dict[str, str] = {}

class Event(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    session_id: str = Field(max_length=100)
    audience: Literal['consumer','reseller'] = 'consumer'
    path: str = Field(max_length=500)
    properties: dict = {}
    attribution: dict[str,str] = {}

class StatusUpdate(BaseModel):
    status: str

class Record(BaseModel):
    id: str
    model_config = {'extra':'allow'}