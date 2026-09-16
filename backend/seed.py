from db import db, now

PRODUCTS = [
    ('classic','Classic','The OG crunch.','#ef482b','#f3ded1'),
    ('garlic','Garlic','Bold. Savoury. Unmissable.','#dba932','#f3e9bd'),
    ('peri-peri','Peri Peri','Turn up the heat.','#2b4ed4','#dfe3ef'),
    ('diet','Diet','A different kind of crunch.','#245c4c','#e7ebe0'),
]
CONFIG = {
    'announcement': 'FOUR FLAVOURS. ENDLESS CRUNCH. BUILD YOUR OWN SANGLEY BOX.',
    'hero': {'eyebrow':'BORN IN SANGLI. MADE FOR YOUR EVERYDAY.', 'line1':'SMALL TOWN.', 'line2':'BIG CRUNCH.', 'description':'Meet Bhadang. Maharashtra’s much-loved puffed rice snack, with a whole new attitude. Four flavours. One very good reason to take a break.'},
    'story': 'We come from Sangli, Maharashtra. And we’re taking a little of it with us. SANGLEY starts with Bhadang—a puffed rice snack with a place in our everyday. Our next chapter? More flavours, more tables, and more people sharing the crunch.',
    'whatsapp_number':'', 'support_email':'', 'instagram_url':'', 'youtube_url':'',
    'shipping_text':'Shipping charges and delivery timelines will be confirmed by our team before you pay. This website currently accepts order enquiries.',
    'checkout_mode':'enquiry',
    'bundles':[
        {'size':4,'title':'The first crunch','recommendation':'FIRST TIME TRYING SANGLEY?','use_case':'A little of everything. Perfect for discovering your favourite.','price':None,'enabled':True,'mix_match':True,'offer':''},
        {'size':6,'title':'The sharing box','recommendation':'CAN’T PICK JUST ONE?','use_case':'For office breaks, family time, and the friend who always asks for a bite.','price':None,'enabled':True,'mix_match':True,'offer':''},
        {'size':8,'title':'The full house','recommendation':'STOCKING UP?','use_case':'For parties, gifting, and making sure the snack shelf is never empty.','price':None,'enabled':True,'mix_match':True,'offer':''}
    ],
    'reseller': {
        'headline':'YOUR COMMUNITY. YOUR NEXT CHAPTER.',
        'description':'Turn the community you already have into your customer base. Introduce SANGLEY to the people who know you.',
        'cost_per_pack':None,'selling_price':149,
        'kits':[
            {'id':'starter','name':'Starter','description':'Make your first introduction.','price':None,'quantity':None,'margin':None,'products':[],'contents':'','offer':'','enabled':True},
            {'id':'growth','name':'Growth','description':'Bring more people to the table.','price':None,'quantity':None,'margin':None,'products':[],'contents':'','offer':'','enabled':True},
            {'id':'pro','name':'Pro','description':'Explore a bigger starting point.','price':None,'quantity':None,'margin':None,'products':[],'contents':'','offer':'','enabled':True}
        ],
        'resources':[], 'community_stories':[]
    },
    'faqs':[
        {'question':'So, what exactly is Bhadang?','answer':'Bhadang is a puffed rice snack associated with Maharashtra. SANGLEY introduces it in four flavours: Classic, Garlic, Peri Peri and Diet. See each product page for confirmed product details as they become available.'},
        {'question':'Can I mix flavours in a box?','answer':'Absolutely. Choose 4, 6 or 8 packs and make your own mix. All one flavour, a little of each, or anything in between. Each pack is 200g.'},
        {'question':'How much does a pack cost?','answer':'The current planned price is ₹149 per 200g pack. Your box total is shown as you build it. Shipping and final fulfilment details are confirmed before payment.'},
        {'question':'Do I need a shop to become a reseller?','answer':'No physical shop is necessary. You can introduce SANGLEY to your housing society, friends, family, office or wider community. Share your details and our team will discuss suitable starting options.'},
        {'question':'How do orders work right now?','answer':'Submit a guest order enquiry with your selection and delivery details. Our team will confirm availability, shipping and payment arrangements. No payment is collected on this website.'}
    ],
    'testimonials':[], 'ugc':[], 'offers':[], 'articles':[],
    'policies':{'shipping':'','returns':'','privacy':'','terms':''},
    'theme':{'brand':'#ee4728','cream':'#f7f2e7','ink':'#24251f','blue':'#284cd4','success':'#28674e','warning':'#a96912'}
}

async def seed_content():
    for i,(slug,flavour,personality,color,bg) in enumerate(PRODUCTS):
        product = {'id':slug,'handle':f'{slug}-bhadang','title':f'{flavour} Bhadang','flavour':flavour,'sku':f'SNG-BHD-{slug.upper()}-200','category':'bhadang','vendor':'SANGLEY','price':149,'mrp':None,'weight':200,'description':f'Meet your {flavour.lower()} crunch. Sangli roots. A fresh SANGLEY attitude.','personality':personality,'flavour_profile':'','ingredients':'','nutrition':'','storage':'','images':[f'/assets/{slug}.webp'],'image_labels':['Front packaging concept'],'concept_images':True,'available':True,'badge':'','color':color,'background':bg,'seo_title':f'{flavour} Bhadang, 200g | SANGLEY','seo_description':f'Explore SANGLEY {flavour} Bhadang. 200g at ₹149. Buy a pack or build a mixed box.','featured_order':i,'sales_count':0,'created_at':now(),'metafields':{}}
        await db.products.update_one({'id':slug},{'$setOnInsert':product},upsert=True)
    await db.content.update_one({'id':'site'},{'$setOnInsert':{'id':'site',**CONFIG}},upsert=True)
    await db.products.create_index('id',unique=True)
    await db.products.create_index('handle',unique=True)
    await db.orders.create_index('request_id',unique=True)
    await db.events.create_index('created_at')