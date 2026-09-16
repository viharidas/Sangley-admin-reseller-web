from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional

class ContentBase(BaseModel):
    model_config=ConfigDict(allow_inf_nan=False,extra='forbid')

class HeroContent(ContentBase):
    eyebrow:str
    line1:str=Field(min_length=1,max_length=35)
    line2:str=Field(min_length=1,max_length=35)
    description:str

class BundleContent(ContentBase):
    size:int
    title:str
    recommendation:str
    use_case:str
    price:Optional[float]=Field(default=None,ge=0)
    enabled:bool=True
    mix_match:bool=True
    offer:str=''

class KitContent(ContentBase):
    id:str
    name:str
    description:str=''
    price:Optional[float]=Field(default=None,ge=0)
    quantity:Optional[int]=Field(default=None,ge=1)
    margin:Optional[float]=Field(default=None,ge=0)
    products:list[str]=[]
    contents:str=''
    offer:str=''
    enabled:bool=True

class Resource(ContentBase):
    title:str
    url:str
    active:bool=False

class Review(ContentBase):
    name:str
    product:str
    review:str
    rating:Optional[float]=Field(default=None,ge=1,le=5)
    image:str=''
    published:bool=False

class UGC(ContentBase):
    image:str
    caption:str
    published:bool=False

class FAQContent(ContentBase):
    question:str=Field(min_length=1)
    answer:str=Field(min_length=1)

class ResellerContent(ContentBase):
    headline:str
    description:str
    cost_per_pack:Optional[float]=Field(default=None,ge=0)
    selling_price:Optional[float]=Field(default=None,ge=0)
    kits:list[KitContent]
    resources:list[Resource]=[]
    community_stories:list[dict]=[]

class Offer(ContentBase):
    title:str
    description:str
    link:str='/shop'
    cta:str='EXPLORE'
    active:bool=False
    @field_validator('link')
    @classmethod
    def safe_link(cls,value):
        if not value.startswith('/') or value.startswith('//'): raise ValueError('Use an internal page path for offers')
        return value

class Policies(ContentBase):
    shipping:str=''
    returns:str=''
    privacy:str=''
    terms:str=''

class Theme(ContentBase):
    brand:str
    cream:str
    ink:str
    blue:str
    success:str
    warning:str
    @field_validator('*')
    @classmethod
    def color(cls,value):
        import re
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',value): raise ValueError('Theme colours must be six-digit hex values')
        return value

class SiteContent(ContentBase):
    id:str='site'
    announcement:str
    hero:HeroContent
    story:str
    whatsapp_number:str=''
    support_email:str=''
    instagram_url:str=''
    youtube_url:str=''
    shipping_text:str
    checkout_mode:str='enquiry'
    bundles:list[BundleContent]
    reseller:ResellerContent
    faqs:list[FAQContent]
    testimonials:list[Review]=[]
    ugc:list[UGC]=[]
    offers:list[Offer]=[]
    articles:list[dict]=[]
    policies:Policies
    theme:Theme
    @field_validator('instagram_url','youtube_url')
    @classmethod
    def safe_url(cls,value):
        if value and not value.startswith('https://'): raise ValueError('Use a valid HTTPS URL')
        return value