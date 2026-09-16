# SANGLEY 2.0 — Product Requirements & Handoff

## Original problem statement
Build a completely NEW SANGLEY website, not a modification or visual copy of an existing site. SANGLEY is a modern Indian snack brand originating in Sangli, Maharashtra. Use https://svasthyaa.com only for UX principles and information architecture: easy product discovery, categories, bundles, storytelling, trustworthy social proof, rich product pages and a simple ecommerce journey. Create a distinct modern, bold, young, premium, appetising Indian identity around **CRUNCH + COMMUNITY**.

The launch is **BHADANG FIRST**: Classic, Garlic, Peri Peri and Diet, 200g, planned price ₹149. No invented flavours, ingredients, nutrition, health claims, certifications, history, testimonials, manufacturing claims, discounts or earnings. Support 4/6/8-pack same-flavour and mix-and-match boxes. Keep future category architecture scalable without launching raisins, turmeric or jaggery.

Two separate journeys: **Eat SANGLEY** (discover → choose flavour → build combo → cart → checkout) and **Sell SANGLEY** (discover community reselling → understand options → contact → onboard → sell/reorder/grow). Resellers may sell to societies, neighbours, family, friends, offices, colleges and WhatsApp/social groups; a shop is not necessary. Provide a dedicated conversion-focused reseller experience, configurable starter options/economics, transparent illustrative calculator, lead form, WhatsApp contact, toolkit/community slots and a simple reseller CRM.

Requested pages/features: homepage, shop/filters/sorting, premium product pages/galleries, combo destination and live builder, reseller page/onboarding, Our Story, FAQ, Contact, policies/offers, cart drawer, account-ready orders/addresses/profile/wishlist/reorder, admin/content architecture, analytic events split by consumer/reseller, SEO metadata/schema/social sharing, future content and Shopify-ready products/variants/collections/metafields/customer/order architecture. Original SANGLEY Bhau/Tai brand character concepts. Mobile-first at 360/390/430px; desktop 1440px with 1200–1280px content. Performance and restrained premium animation.

Additional user direction: Awwwards-style craft with a distinctive coherent art direction, kinetic masked line-by-line hero reveal, deliberate product imagery, numbered editorial chapters, one slow marquee, framer-motion scroll reveals and micro-interactions, Lenis momentum scrolling and a subtle 3D/parallax hero.

## Explicit user choices
- Build with clearly labelled concept packaging; keep missing facts, reseller economics and WhatsApp contact unpublished and editable.
- Protected admin and guest shopping; customer registration/sign-in deferred.
- Checkout question skipped. Adopted and communicated default: **saved order enquiry, no online payments**, pending shipping and payment arrangements.
- No existing brand assets were supplied. Generated concept assets are clearly disclosed as such, not represented as real product photography.

## Architecture
- React 19 / React Router, custom token-based CSS, Shadcn buttons/sheets/toaster, Framer Motion 11, Lenis.
- FastAPI, Pydantic validation, Motor/MongoDB. Existing protected DB/URL environment keys retained.
- Mongo collections: `products`, `content`, `users`, `orders`, `leads`, `events`, `login_attempts`.
- Stable string IDs and handles, SKU, vendor, category, attributes and metafields. All Mongo responses exclude BSON `_id`.
- Guest cart/wishlist/enquiry references persist on the same browser/device. PII is not included in the local enquiry history. Server computes cart/order prices; client totals are never trusted.
- Order requests are idempotent using a unique request_id. Orders start ENQUIRY / NOT_COLLECTED. Shipping remains unconfirmed until team follow-up.
- Admin: bcrypt password hash, 15-minute access/7-day refresh HttpOnly Secure cookies, explicit Origin validation, role/user checks, database-backed login throttling. No public registration endpoint. Credentials in `test_credentials.md`.
- Important origin RCA: the gateway rewrites the public origin to the verified cluster host. `SANGLEY_TRUSTED_ORIGINS` in backend .env explicitly lists the public and observed gateway origins. Both CORS and auth use that allowlist; no wildcard auth exceptions. Do not replace it with permissive suffix matching.
- Hosted image URL editing, not user file uploads. Generated optimized WebP assets are bundled under frontend/public/assets. No user files are stored on ephemeral disk.

## Implemented
### Shopping
- Motion-led original vermilion/oat/cobalt identity; Barlow Condensed + DM Sans + DM Serif Display, limited Caveat annotations; responsive hero with layered concept packs, flavour switching, 3D pointer tilt, masked text entrance, reduced-motion respect, editorial chapters and slow marquee.
- Four seeded products at ₹149 / 200g. Shop filters (flavour, availability, price, pack size) and sorting. Wishlist, gallery support, per-flavour routes, editable factual accordions, genuine-only review slots.
- Dedicated combo landing page, contextual 4/6/8 recommendations, interactive visual box filling, counters, same-flavour shortcuts, reset, live price/count, validated add-to-cart.
- Persistent cart drawer, live server price quotes, quantity/removal, guest enquiry form, reference confirmation and same-device enquiry/reorder history.
- Story, Bhau/Tai character concepts, FAQ, Contact, editable offers, safe unpublished policy notices, social/UGC spaces.
### Community
- Distinct cobalt reseller experience, traditional-vs-community flow, 3-step explainer, configurable Starter/Growth/Pro options.
- Calculator: quantity and selling value work now; cost/margin only shown after approved pricing is supplied. No guaranteed earnings.
- Lead form with consent, community type/network size/starting option, contact details and campaign attribution. Separate consumer contact enquiries.
- WhatsApp-prefilled links and mobile CTA activate with an approved number. Until then, contact CTAs lead to the working enquiry form.
- Toolkit resources can be activated via real hosted resource links. No fabricated resources, sellers or achievements.
### Owner operations
- /admin login, overview, product creation/edit/delete, factual fields, hosted image galleries, pricing/availability/SKU/SEO, content publishing.
- Easy form inputs for hero/announcement/story/shipping/contact/social. Structured validated JSON editor for bundles, reseller packages/economics/resources, FAQs, testimonials, UGC, offers, policies, theme and future articles.
- Reseller/consumer leads distinguished; CRM states NEW LEAD, CONTACTED, INTERESTED, ONBOARDING, ACTIVE, FIRST ORDER, REPEAT ORDER, INACTIVE. Order enquiry statuses independently configurable through allowed status transitions.
- Search/filter records, order contents and delivery detail views, first-party analytics by audience, campaign data in records, downloadable Shopify-oriented JSON export.
- Per-route SEO/canonical/JSON-LD, static OG fallback, original favicon. Enquiries are tracked as order_enquiry, NOT purchase. Purchase event reserved for actual paid integration later.

## Routes & key APIs
Public pages: `/`, `/shop`, `/products/:handle`, `/collections/combos`, `/resell-with-sangley`, `/our-story`, `/faq`, `/contact`, `/offers`, `/policies/:type`, `/account`, `/checkout`, `/admin`.
Public API: GET `/api/`, `/api/products`, `/api/products/:handle`, `/api/content`; POST `/api/cart/quote`, `/api/orders`, `/api/leads`, `/api/events`.
Admin API: `/api/auth/login|me|refresh|logout`; `/api/admin/overview|products/:id|content|leads|leads/:id|orders|orders/:id|analytics|export`.

## Testing and verification
- Initial testing found origin rewrite rejection, empty-cart navigation issue, duplicate footer keys and injected option-span hydration warning. All fixed.
- Existing backend suite: **12/12 passed** after auth correction.
- Focused admin/CMS suite: **7/7 passed**. Product edits, content edits, calculator economics, WhatsApp links, lead/order statuses, export, analytics, invalid CMS rejection, unauthorized denial verified. All business changes restored.
- Browser flow passes: flavour discovery, cart, 4-pack ₹596, guest order enquiry confirmation, reseller lead, wishlist persistence, same-device records, admin sign-in/editing, empty cart CTA closing.
- Mobile settled views and overflow checks passed at 360/390/430; desktop checked at 1440 and 1920. No remaining issues in iteration_2 report. Production build passes.
- Reports: `/app/test_reports/iteration_1.json`, `/app/test_reports/iteration_2.json`, pytest XML reports and screenshots.
- Only QA TEST-named generated enquiry/lead records were removed after verification. Catalog restored to ₹149; WhatsApp blank; reseller cost_per_pack null. Analytics currently include development/testing activity.

## Prioritized backlog / next tasks
### P0 — Business facts before taking payment (owner inputs)
1. Supply real packaging/product photography, verified ingredients/allergens/nutrition/storage, final prices and SKUs. Replace concept assets and turn concept flags off only for real assets.
2. Supply WhatsApp number/support contacts; approve shipping/returns/privacy/terms and customer-facing availability/fulfilment terms.
3. Confirm reseller prices, quantities, package contents and margin basis; publish only approved figures.
### P1 — Next operational features
1. Confirm payment provider and shipping/fulfilment flow before adding real checkout payments; currently enquiries only.
2. Add notification delivery for orders/leads and owner-friendly dedicated forms for advanced JSON sections.
3. Actual signed-in customer accounts/addresses/order tracking when wanted; guest pages explicitly explain current scope.
4. Genuine review moderation and real customer UGC/content collection. Support resources only when produced.
### P2 — Scale
1. Shopify import adapter/theme mapping and commerce API integration; current export is migration-ready foundation, not an installed Shopify store.
2. Activated articles/blog, reseller resource library/community stories, future category collections when products are ready.
3. Dedicated reseller accounts/reorder portal, fulfilment/inventory integrations, richer campaign attribution and consent controls.

## Known scope boundaries
No payment provider, email/SMS notifications, customer auth, real photos, approved product facts, reseller economics, shipping policy or real testimonials were supplied/activated. These are deliberate, honestly represented business readiness states, not simulated working integrations. WhatsApp becomes functional when an actual number is supplied. API/database flows are real; no mocked API responses.